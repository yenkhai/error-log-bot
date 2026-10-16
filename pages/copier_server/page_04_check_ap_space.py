"""AP disk space summary: red Use% or usage >80% is Tier 1."""
from core.base_checker import BaseChecker
from core.checkpoint_store import CheckpointStore
from core.colors import red_cell


def space_rows(servers):
    rows, errors = [], []
    for server in servers:
        cell = server.get("use") or {}
        missing = [label for key, label in (("size", "Size"), ("used", "Used"), ("avail", "Avail"))
                   if not str(server.get(key, "")).strip() or str(server.get(key, "")).strip() == "-"]
        try:
            percent = float(cell.get("text", "").strip().rstrip("%"))
        except (ValueError, TypeError):
            percent = None
            missing.append("Use%")
        reason = "connection die" if server.get("connectionDie") else ""
        if missing:
            reason = (reason + "; " if reason else "") + "缺少 " + ", ".join(missing)
        bad = bool(reason) or (percent is not None and percent > 80) or red_cell(cell)
        if bad:
            errors.append(f"{server['ip']}: {reason or cell.get('text', '')}")
        rows.append([CheckpointStore.make_cell(server.get(key) or "-", "red" if reason and key == "ip" else "white")
                     for key in ("ip", "size", "used", "avail")] +
                    [CheckpointStore.make_cell(reason or cell.get("text", "-"), "red" if bad else "green")])
    if not rows:
        raise RuntimeError("未捕获到 AP Space 数据")
    return rows, errors


class CheckAPSpaceChecker(BaseChecker):
    def check(self) -> bool:
        self.log_station_header("第04站 Check AP Space", menu_id="apy_b0i22text")
        try:
            self.navigate_to_menu("Check AP Space", menu_id="apy_b0i22text", section="Copier")
            self.wait_for_page_loaded(seconds=2, max_wait=30)
            servers = self.driver.execute_script(r"""
                const result = [];
                for (const header of document.querySelectorAll('[id$="_hedder"]')) {
                    const ip = header.id.slice(0, -7);
                    if (!/^\d{1,3}(?:\.\d{1,3}){3}$/.test(ip)) continue;
                    const data = header.nextElementSibling;
                    const text = data ? data.innerText : '';
                    const connectionDie = /connection\s+die/i.test(text);
                    let found = false;
                    if (data) for (const table of data.querySelectorAll('table')) {
                        const ownRows = Array.from(table.rows).filter(r => r.closest('table') === table);
                        const heading = ownRows.find(r => Array.from(r.cells).some(c => c.innerText.trim() === 'Use%'));
                        if (!heading) continue;
                        const labels = Array.from(heading.cells).map(c => c.innerText.trim());
                        for (const row of ownRows) {
                            if (row === heading) continue;
                            const cells = Array.from(row.cells);
                            if (!cells.length || cells.some(c => c.querySelector('table'))) continue;
                            const value = label => {
                                const index = labels.indexOf(label);
                                return index >= 0 ? cells[index] : null;
                            };
                            const useCell = value('Use%');
                            const style = useCell ? getComputedStyle(useCell) : null;
                            result.push({ip, connectionDie,
                                size: value('Size')?.innerText.trim() || '',
                                used: value('Used')?.innerText.trim() || '',
                                avail: value('Avail')?.innerText.trim() || '',
                                use: {text: useCell?.innerText.trim() || '',
                                      css_bg: style?.backgroundColor || '', fg: style?.color || ''}});
                            found = true;
                        }
                    }
                    if (!found) result.push({ip, connectionDie, size: '', used: '', avail: '', use: {text: ''}});
                }
                return result;
            """)
            rows, errors = space_rows(servers)
            passed = not errors
            for item in errors:
                self.log(f"[ERROR] AP Space {item}，连接、数据缺失或 Use% 异常，Tier 1")
            msg = f"{len(errors)} 项 Use% 异常，Tier 1 阻断 Checkpoint" if errors else f"全部 {len(rows)} 项磁盘空间正常"
            self.log_check_result(passed, msg)
            CheckpointStore.save(page_key="copier_04", title="Check AP Space", status=passed,
                                 headers=["IP Address", "Size", "Used", "Avail", "Use%"], rows=rows, summary=msg)
            if not passed:
                return False
            if not self.click_checkpoint():
                raise RuntimeError("Checkpoint button could not be submitted; retry this station")
            return True
        except Exception as exc:
            return self.handle_exception("copier_04", "Check AP Space", exc)
