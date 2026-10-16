"""Info Robot: only green TimeStamp backgrounds pass inspection."""
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore


class InfoRobotMonitorChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第09站 Info Robot Monitor", menu_id="apy_b0i27text")
        try:
            self.navigate_to_menu("Info Robot Monitor", menu_id="apy_b0i27text", section="Copier")
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
                        result.push({values, green});
                    }
                }
                return result;
            """)
            if not robots:
                raise RuntimeError("未捕获到 Info Robot TimeStamp 数据")
            rows = []
            errors = 0
            for robot in robots:
                values = robot["values"]
                if not robot["green"]:
                    errors += 1
                    self.log(f"[ERROR] Info Robot {values[0]} ({values[1]}): TimeStamp 非绿色，Tier 1")
                rows.append(values[:3] + [CheckpointStore.make_cell(values[3], "green" if robot["green"] else "red")])
            passed = errors == 0
            msg = (f"{errors} 个 Robot 的 TimeStamp 非绿色，Tier 1 阻断 Checkpoint"
                   if errors else f"全部 {len(robots)} 个 Robot 的 TimeStamp 为绿色")
            self.log_check_result(passed, msg)
            CheckpointStore.save(page_key="copier_09", title="Info Robot Monitor", status=passed,
                                 headers=["Robot ID", "Details", "Robot Interval", "TimeStamp"],
                                 rows=rows, summary=msg)
            if not passed:
                return False
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            return True
        except Exception as exc:
            return self.handle_exception("copier_09", "Info Robot Monitor", exc)
