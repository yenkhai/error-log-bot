"""Error Log: >5000 records warns; >8000 blocks Checkpoint."""
import re

from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


def record_tier(count):
    return "TIER1" if count > 8000 else "TIER3" if count > 5000 else "OK"


class ErrorLogChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第05站 Error Log", menu_id="apy_b0i23text")
        try:
            self.navigate_to_menu("Error Log", menu_id="apy_b0i23text", section="Copier")
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            servers = self.driver.execute_script(r"""
                const result = [], seen = new Set(), groups = new Map();
                for (const table of document.querySelectorAll('table')) {
                    if (!/Server/i.test(table.innerText) || !/Total/i.test(table.innerText)) continue;
                    for (const row of table.rows) {
                        const cells = Array.from(row.cells);
                        if (cells.length !== 2 || cells.some(c => c.querySelector('table'))) continue;
                        const server = cells[0].innerText.trim(), total = cells[1].innerText.trim();
                        if (!server || !total || /[\r\n]/.test(server) ||
                            /^(Server|Total|Summary)$/i.test(server) || !/^(No Error|[\d,]+(?:\s+Records?)?)$/i.test(total)) continue;
                        if (seen.has(server)) continue;
                        seen.add(server);
                        const owner = row.closest('table');
                        if (!groups.has(owner)) groups.set(owner, groups.size);
                        result.push({server, total, group: groups.get(owner)});
                    }
                }
                return result;
            """)
            if not servers:
                raise RuntimeError("未捕获到 Error Log 服务器数据")
            rows, details, grouped_rows = [], [], {}
            errors = warnings = 0
            for srv in servers:
                match = re.search(r"[\d,]+", srv["total"])
                count = int(match.group().replace(",", "")) if match else 0
                tier = record_tier(count)
                errors += tier == "TIER1"
                warnings += tier == "TIER3"
                color = "red" if tier == "TIER1" else "yellow" if "record" in srv["total"].lower() else "green"
                rows.append([CheckpointStore.make_cell(srv["server"], "white"),
                             CheckpointStore.make_cell(srv["total"], color)])
                grouped_rows.setdefault(srv["group"], []).append(rows[-1])
                if tier != "OK":
                    details.append(f"{srv['server']}: {srv['total']} ({tier})")
            self.log_check_method("Records >8000: Tier 1 阻断；>5000: Tier 3 提醒；<=5000: 正常")
            self.log_data_summary(details)
            passed = errors == 0
            msg = (f"Tier 1: {errors} 台，Tier 3: {warnings} 台" if errors or warnings
                   else f"全部 {len(servers)} 台服务器记录数正常")
            self.log_check_result(passed, msg)
            tables = [{"headers": ["Server", "Total"], "rows": group_rows,
                       "header_bg": "#BCD493"} for group_rows in grouped_rows.values()]
            CheckpointStore.save(page_key="copier_05", title="Error Log", status=passed,
                                 tables=tables, summary=msg,
                                 has_warn=warnings > 0)
            if not passed:
                return False
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            return True
        except Exception as exc:
            return self.handle_exception("copier_05", "Error Log", exc)
