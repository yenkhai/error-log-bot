"""NIW Robot: inspect all RCM/LRCM timestamp backgrounds; non-green blocks."""
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class NIWRobotMonitorChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第08站 NIW Robot Monitor", menu_id="apy_b0i26text")
        try:
            self.navigate_to_menu("NIW Robot Monitor", menu_id="apy_b0i26text", section="Copier")
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            robots = self.driver.execute_script(r"""
                const result = [];
                for (const table of document.querySelectorAll('table')) {
                    if (!/TimeStamp/i.test(table.innerText) || !/Robot/i.test(table.innerText)) continue;
                    for (const row of table.rows) {
                        const cells = Array.from(row.cells);
                        if (cells.length !== 4 || cells.some(c => c.querySelector('table'))) continue;
                        const values = cells.map(c => c.innerText.trim());
                        if (!/^\d+$/.test(values[0])) continue;
                        const color = getComputedStyle(cells[3]).backgroundColor;
                        const rgb = color.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
                        const green = !!rgb && +rgb[2] >= 100 && +rgb[2] > +rgb[1] * 1.3 &&
                                      +rgb[2] > +rgb[3] * 1.3 && (rgb[4] === undefined || +rgb[4] > 0);
                        const container = row.closest('#lrcmlist, #rcmlist');
                        const group = container ? (container.id === 'lrcmlist' ? 'LRCM' : 'RCM') :
                                      (/LRCM/i.test(table.innerText) ? 'LRCM' : 'RCM');
                        result.push({values, green, group});
                    }
                }
                return result;
            """)
            if not robots:
                raise RuntimeError("未捕获到 NIW Robot TimeStamp 数据")
            tables = []
            errors = 0
            for group in ("RCM", "LRCM"):
                rows = []
                for robot in robots:
                    if robot["group"] != group:
                        continue
                    values = robot["values"]
                    if not robot["green"]:
                        errors += 1
                        self.log(f"[ERROR] NIW Robot {group} {values[0]} ({values[1]}): TimeStamp 非绿色，Tier 1")
                    rows.append([CheckpointStore.make_cell(v, "white") for v in values[:3]] +
                                [CheckpointStore.make_cell(values[3], "green" if robot["green"] else "red")])
                tables.append({"title": f"{group} Details",
                               "headers": ["Robot ID", f"{group} Details", "Robot Interval", "TimeStamp"],
                               "rows": rows})
            passed = errors == 0
            msg = (f"{errors} 个 Robot 的 TimeStamp 非绿色，Tier 1 阻断 Checkpoint"
                   if errors else f"全部 {len(robots)} 个 Robot 的 TimeStamp 为绿色")
            self.log_check_result(passed, msg)
            CheckpointStore.save(page_key="copier_08", title="NIW Robot Monitor", status=passed,
                                 tables=tables, summary=msg)
            if not passed:
                return False
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            return True
        except Exception as exc:
            return self.handle_exception("copier_08", "NIW Robot Monitor", exc)
