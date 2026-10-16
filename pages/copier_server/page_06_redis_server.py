"""Redis Server: only red Total cells are Tier 1 errors."""
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore
from core.native_tables import capture_native_tables
from core.colors import red_cell


def redis_display_tables(tables):
    result, errors = [], []
    for table in tables:
        headers = table.get("headers", [])
        totals = [i for i, h in enumerate(headers) if str(h).strip().lower() == "total"]
        if not totals or not any(str(h).strip().lower() == "server" for h in headers):
            continue
        rows = []
        for row in table.get("rows", []):
            row = list(row)
            for index in totals:
                cell = row[index]
                bad = red_cell(cell)
                text = cell.get("text", "") if isinstance(cell, dict) else str(cell)
                if bad:
                    identity = row[0].get("text", "") if isinstance(row[0], dict) else str(row[0])
                    errors.append(f"{identity}: {text}")
                row[index] = {**(cell if isinstance(cell, dict) else {}), "text": text,
                              "bg": "red" if bad else "green",
                              "css_bg": "#FF0000" if bad else "#00D000", "fg": "#000000"}
            rows.append(row)
        if rows:
            result.append({**table, "rows": rows})
    if not result:
        raise RuntimeError("未捕获到 Redis Server Total 数据")
    return result, errors


class RedisServerChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第06站 Redis Server", menu_id="apy_b0i24text")
        try:
            self.navigate_to_menu("Redis Server", menu_id="apy_b0i24text", section="Copier")
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            tables, errors = redis_display_tables(capture_native_tables(self.driver))
            passed = not errors
            for item in errors:
                self.log(f"[ERROR] Redis Server Total 红色异常: {item}，Tier 1")
            msg = f"{len(errors)} 项 Total 红色异常，Tier 1 阻断 Checkpoint" if errors else "全部服务器 Total 无红色异常"
            self.log_check_result(passed, msg)
            CheckpointStore.save(page_key="copier_06", title="Redis Server", status=passed,
                                 tables=tables, summary=msg)
            if not passed:
                return False
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            return True
        except Exception as exc:
            return self.handle_exception("copier_06", "Redis Server", exc)
