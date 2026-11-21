"""
app/guardrails/sql_validator.py - Deterministic SQL Safety Validator using sqlglot.
Enforces read-only SQLite dialect rules, rejects dangerous statements/functions/internal tables,
injects auto-LIMIT clauses, and detects expensive queries.
"""

from typing import Optional, List, Set, Tuple
import sqlglot
from sqlglot import exp, errors

from app.config import settings
from app.agents.models import ValidationResult

PROHIBITED_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Pragma,
    exp.Command,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
)

DANGEROUS_FUNCTIONS = {
    "load_extension",
    "writefile",
    "readfile",
    "edit",
    "system",
    "eval",
}

DEFAULT_KNOWN_TABLES = {
    "categories",
    "products",
    "customers",
    "orders",
    "order_items",
    "payments",
    "reviews",
}


class SQLValidator:
    """Validates and rewrites SQL queries for strict read-only safety and performance."""

    def __init__(
        self,
        default_limit: int = 100,
        max_limit_cap: int = 1000,
        known_tables: Optional[Set[str]] = None,
    ):
        self.default_limit = default_limit
        self.max_limit_cap = max_limit_cap
        self.known_tables = {t.lower() for t in (known_tables or DEFAULT_KNOWN_TABLES)}

    def validate_and_rewrite(
        self,
        sql: str,
        allowed_tables: Optional[Set[str]] = None,
    ) -> ValidationResult:
        """
        Validates SQL string against safety rules and applies auto-LIMIT.
        Returns ValidationResult with is_safe, reason, rewritten_sql, and is_expensive.
        """
        if not sql or not sql.strip():
            return ValidationResult(
                is_safe=False,
                reason="Query is empty.",
            )

        # 1. Parse using SQLite dialect
        try:
            parsed = sqlglot.parse(sql, read="sqlite")
        except errors.ParseError as e:
            return ValidationResult(
                is_safe=False,
                reason=f"SQL syntax error / unparseable query: {str(e)}",
            )
        except Exception as e:
            return ValidationResult(
                is_safe=False,
                reason=f"Failed to parse SQL: {str(e)}",
            )

        # 2. Exactly one statement
        if len(parsed) != 1:
            return ValidationResult(
                is_safe=False,
                reason=f"Rejected multi-statement query: found {len(parsed)} statements. Only single-statement queries are allowed.",
            )

        stmt = parsed[0]

        # 3. Must be a SELECT (or Union of Selects)
        if not isinstance(stmt, (exp.Select, exp.Union)):
            return ValidationResult(
                is_safe=False,
                reason=f"Statement must be a SELECT. Found: {type(stmt).__name__}.",
            )

        # 4. AST walk to check for prohibited DML / DDL / Command nodes anywhere in the tree
        for node in stmt.walk():
            if isinstance(node, PROHIBITED_NODES):
                return ValidationResult(
                    is_safe=False,
                    reason=f"Prohibited SQL operation detected: {type(node).__name__} is not allowed in read-only queries.",
                )

        # 5. Check for dangerous function calls (e.g. load_extension)
        for func in stmt.find_all(exp.Anonymous):
            func_name = func.name.lower() if func.name else ""
            if func_name in DANGEROUS_FUNCTIONS:
                return ValidationResult(
                    is_safe=False,
                    reason=f"Prohibited function detected: '{func_name}' is not allowed.",
                )

        # 6. Check tables for internal/sqlite_ tables and unknown tables
        tables_to_check = {t.lower() for t in allowed_tables} if allowed_tables else self.known_tables
        # Also collect CTE names so they are not flagged as unknown tables
        cte_names = {cte.alias_or_name.lower() for cte in getattr(stmt, "ctes", [])}

        for table in stmt.find_all(exp.Table):
            table_name = table.name.lower() if table.name else ""
            # Block internal sqlite tables
            if table_name.startswith("sqlite_"):
                return ValidationResult(
                    is_safe=False,
                    reason=f"Access to SQLite internal schema table '{table_name}' is prohibited.",
                )

            # Block unknown tables unless it's a declared CTE
            if tables_to_check and table_name not in tables_to_check and table_name not in cte_names:
                return ValidationResult(
                    is_safe=False,
                    reason=f"Table '{table_name}' does not exist in schema. Allowed tables: {sorted(list(tables_to_check))}",
                )

        # 7. Check for Expensive Queries (Cross Join / missing ON / Cartesian)
        is_expensive = self._detect_expensive_patterns(stmt)

        # 8. Auto-LIMIT injection and enforcement
        rewritten_sql = self._apply_auto_limit(stmt)

        return ValidationResult(
            is_safe=True,
            reason=None,
            rewritten_sql=rewritten_sql,
            is_expensive=is_expensive,
        )

    def _detect_expensive_patterns(self, stmt: exp.Expression) -> bool:
        """
        Detects Cartesian joins, cross joins without LIMIT, or massive unindexed joins.
        Note: A CROSS JOIN or Cartesian join with an explicit small LIMIT (<= 100) is cheap in SQLite
        ONLY when there is no ORDER BY, GROUP BY, DISTINCT, or aggregate function,
        because SQLite can early-terminate after fetching the requested limit rows.
        If sorting, grouping, deduplicating, or aggregation is present, SQLite must materialize
        the entire Cartesian product before applying the LIMIT, making the query expensive.

        EXCEPTION: If the relations being cross joined are single-row subqueries/CTEs (e.g. aggregate
        queries without GROUP BY, or queries with LIMIT 1), the Cartesian product produces at most
        1 row (1 x 1 = 1) and is therefore computationally trivial.
        """
        joins = list(stmt.find_all(exp.Join))
        if not joins:
            return False

        # Collect CTE definitions
        ctes = {cte.alias_or_name.lower(): cte.this for cte in getattr(stmt, "ctes", [])}

        def _is_single_row_select(node: exp.Expression) -> bool:
            if not isinstance(node, exp.Select):
                return False
            has_agg = bool(list(node.find_all(exp.AggFunc)))
            has_group = bool(node.args.get("group"))
            if has_agg and not has_group:
                return True
            limit_node = node.args.get("limit")
            if limit_node:
                try:
                    if int(limit_node.expression.name) == 1:
                        return True
                except (ValueError, AttributeError):
                    pass
            return False

        def _is_single_row_relation(rel: Optional[exp.Expression]) -> bool:
            if rel is None:
                return False
            if isinstance(rel, exp.Subquery):
                return _is_single_row_select(rel.this)
            elif isinstance(rel, exp.Table):
                name = rel.name.lower() if rel.name else ""
                if name in ctes:
                    return _is_single_row_select(ctes[name])
            return False

        from_node = stmt.find(exp.From)
        from_is_single_row = _is_single_row_relation(from_node.this) if from_node else False

        # Check for clauses that force full materialization of the join product
        has_order_by = bool(stmt.args.get("order"))
        has_group_by = bool(stmt.args.get("group"))
        has_distinct = bool(stmt.args.get("distinct"))
        has_aggregate = bool(list(stmt.find_all(exp.AggFunc)))
        requires_full_materialization = (
            has_order_by or has_group_by or has_distinct or has_aggregate
        )

        # Check if statement has an explicit small LIMIT (<= default_limit)
        limit_node = stmt.args.get("limit")
        has_small_limit = False
        if limit_node is not None and not requires_full_materialization:
            try:
                limit_val = int(limit_node.expression.name)
                if limit_val <= self.default_limit:
                    has_small_limit = True
            except (ValueError, AttributeError):
                has_small_limit = False

        for j in joins:
            # Check if this join is between single-row relations (1 x 1 = 1 row)
            is_single_row_cross = from_is_single_row and _is_single_row_relation(j.this)

            # Explicit CROSS JOIN
            if j.kind and "CROSS" in j.kind.upper():
                if not is_single_row_cross and not has_small_limit:
                    return True
            # Implicit Cartesian join: Join without ON or USING clause
            elif j.args.get("on") is None and j.args.get("using") is None:
                join_kind = (j.kind or "").upper()
                if "NATURAL" not in join_kind:
                    if not is_single_row_cross and not has_small_limit:
                        return True

        # Multiple joins (>= 3) with no WHERE filter and no small limit
        all_joins_single_row = from_is_single_row and all(_is_single_row_relation(j.this) for j in joins)
        if len(joins) >= 3 and stmt.args.get("where") is None and not has_small_limit and not all_joins_single_row:
            return True

        return False

    def _apply_auto_limit(self, stmt: exp.Expression) -> str:
        """Injects or clamps LIMIT clause on the outermost select query."""
        limit_node = stmt.args.get("limit")
        if limit_node is None:
            # No limit present: inject default limit
            stmt = stmt.limit(self.default_limit)
        else:
            try:
                # Check limit value
                current_val = int(limit_node.expression.name)
                if current_val > self.max_limit_cap:
                    stmt.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit_cap)))
            except (ValueError, AttributeError):
                # If expression is non-literal or invalid, enforce cap
                stmt.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit_cap)))

        return stmt.sql(dialect="sqlite")
