"""Robot Monitor checks timestamp and IP colors; this page has no Checkpoint."""
from core.colors import red_cell
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore
from core.native_tables import capture_native_tables


def monitor_tables(tables):
    display, errors = [], []
    found = set()
    for table in tables:
        headers = table.get("headers", [])
        indices = [i for i, h in enumerate(headers) if "timestamp" in str(h).lower()]
        kind = "TimeStamp"
        if not indices:
            indices = [i for i, h in enumerate(headers) if str(h).strip().lower() == "ip address"]
            kind = "IP Address"
        if not indices:
            continue
        found.add(kind)
        for row in table.get("rows", []):
            for index in indices:
                if index < len(row) and red_cell(row[index]):
                    identity = row[0].get("text", "") if isinstance(row[0], dict) else str(row[0])
                    errors.append(f"{kind}: {identity}")
        keep = [i for i, h in enumerate(headers) if str(h).strip().lower() not in ("action", "actions")]
        projected = {**table, "headers": [headers[i] for i in keep]}
        for key in ("rows", "header_rows"):
            projected[key] = [[row[i] for i in keep] for row in table.get(key, [])]
        for key in ("header_spans", "cell_spans"):
            projected[key] = []
            for span in table.get(key, []):
                columns = [i for i in keep if span["col"] <= i < span["col"] + span.get("colspan", 1)]
                if columns:
                    projected[key].append({**span, "col": keep.index(columns[0]), "colspan": len(columns)})
        display.append(projected)
    if found != {"TimeStamp", "IP Address"} or any(not t.get("rows") for t in display):
        raise RuntimeError("Robot Monitor 的 TimeStamp / IP Address 表格未完整加载")
    return display, errors


class RobotMonitorChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第07站 Robot Monitor", menu_id="apy_b0i25text")
        try:
            self.navigate_to_menu("Robot Monitor", menu_id="apy_b0i25text", section="Copier")
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            tables, errors = monitor_tables(capture_native_tables(self.driver))
            passed = not errors
            for error in errors:
                self.log(f"[ERROR] Robot Monitor {error} 红色异常，Tier 1")
            msg = f"{len(errors)} 项红色异常，Tier 1 阻断" if errors else "TimeStamp 和 IP Address 均无红色异常"
            self.log_check_result(passed, msg)
            CheckpointStore.save(page_key="copier_07", title="Robot Monitor", status=passed,
                                 tables=tables, summary=msg)
            # This station has no Checkpoint button.
            return passed
        except Exception as exc:
            return self.handle_exception("copier_07", "Robot Monitor", exc)
