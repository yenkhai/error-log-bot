# Error Log Bot

Windows 桌面运维工具，包含 NIW / Copier 巡检、Error Log 导出和巡检结果查看。

## 运行与验证

```powershell
python -m pip install -r requirements.txt
python main.py
python -X utf8 -m unittest discover -s scratch -p "test_*.py"
```

运行 `build.bat` 可重新生成 `dist/work.exe`。源码修改不会自动更新已有 EXE。

## 使用行为

- Checkpoint 终端只显示关卡进度、结果、警告/错误和必要操作；表格数据保留在 Log Viewer。
- Check 按下方勾选项执行（NIW → Copier）；没有勾选时会提示，不启动浏览器。
- 「仅 Checkpoint」总开关打开后，在弹窗选择页面并确定保存；设置跨重启保留。选中的页面不检查数据，只确认 Checkpoint 提交；关闭总开关恢复正常检查。未确认的弹窗选择不会应用。
- Robot Monitor 无 Checkpoint；人工 Skip 或仅 Checkpoint 模式直接跳过，日志保留未检查标记。
- Stop 等待当前关卡完成后暂停；Resume 从下一项未执行的关卡继续。检查失败时 Resume 重试失败关卡。
- 暂停时定时调度等待人工继续；选择 Check 会开始新一轮并替换旧续跑位置。
- 登录、巡检、导出共享浏览器，同一时间只执行一个任务。
- 有 Checkpoint 按钮的页面必须确认点击后的状态变化或请求完成；操作失败暂停。无按钮的只读页面保留原有行为。
- 关闭窗口会等待任务停止并清理驱动；接管的调试浏览器保留，工具自行启动的浏览器会关闭。
- 导出文件位于 Windows 实际桌面，文件名含昨天的完整日期，例如 `error log 2026-10-14.txt`。
- 每台服务器完整写入后附带结束标记和校验值，只有完整区块可恢复进度。旧格式与半写入区块保留，重新抓取后追加。
- 导出摘要区分新增导出、恢复进度、超限跳过、失败和未完成；有跳过或失败时不会声称全部导出成功。

## 配置与结构

源码运行读取项目目录的 `config.json`；EXE 运行将配置和崩溃日志保存到 `%LOCALAPPDATA%/ErrorLogBot`，首次运行可迁移 EXE 同目录的旧配置。

- `core/stations.py`：关卡顺序、标题、存储键和检查器的统一清单。
- `services/checkpoint_engine.py`：巡检执行与恢复流程。
- `gui/`：界面、定时触发及主线程消息队列。
- `services/error_log_scraper.py`：日志提取、完整写入、恢复与结果统计。

测试包含模拟故障和界面逻辑；真实内网站点的登录标志、Checkpoint 提交反馈仍需在目标环境验证。

## Log Viewer 原始表格

单页完整表格优先按网站 DOM 保留多层表头、rowspan/colspan、颜色和左右排列。原始采集仅用于显示，不改变巡检判断。逐公司／多 Frame 汇总页面保留完整聚合数据；采集不完整时回退到原有明细。旧的内存结果需重新巡检后才会更新。

各页面的自定义显示（如 AP Space 汇总、Error Log 横向分组、Wallet 精简列）优先于网站原表。CCL Recover、Check CCL、Wsum Sport、HG Percentages 未读取到必要数据时会停止，不将空页面判为通过。
