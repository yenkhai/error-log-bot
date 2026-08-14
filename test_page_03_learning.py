"""
================================================================================
第 3 站 Matches & Wagers 专属独立测试与学习脚本 (test_page_03_learning.py)
--------------------------------------------------------------------------------
【文件用途】
这是一个独立的测试脚本，【不影响现有项目的任何代码】。
您可以随时单独运行此脚本：
    py test_page_03_learning.py
================================================================================
"""

import sys
import time
from core.browser import BrowserManager
from config import load_config
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 设置标准输出编码为 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def main():
    print("=" * 80)
    print(" 🚀 [第 3 站 Matches & Wagers] 独立测试与红字高亮解析脚本")
    print("=" * 80)

    config = load_config()
    user = config.get("AUTH_USER", "op35")
    pwd = config.get("AUTH_PASS", "123qwe")

    print("[1] 正在连接/启动 Chrome 浏览器...")
    driver = BrowserManager.get_driver(user=user, pwd=pwd)
    print("✅ 浏览器连接成功！\n")

    print("[2] 正在导航跳转到 第 3 站 Matches & Wagers (Menu ID: apy_b0i4text)...")
    try:
        driver.switch_to.default_content()
        driver.switch_to.frame(0)
        
        menu_el = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "apy_b0i4text"))
        )
        driver.execute_script("arguments[0].click();", menu_el)
        print("🖱️ 已点击菜单 Matches & Wagers，等待 4 秒加载数据...")
        time.sleep(4)

        driver.switch_to.default_content()
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.NAME, "mainFrame")))
        driver.switch_to.frame("mainFrame")
        print("✅ 已成功切入 mainFrame 数据框架！\n")

    except Exception as e:
        print(f"❌ 页面导航失败: {e}")
        return

    print("[3] 正在结构化解析所有数据（红字/异常节点自动打标）...\n")
    
    js_code = """
    var result = {
        rcmUncompletedScore: {},
        lrcmUncompletedScore: {},
        rcmWagers: [],
        rcmPoly: [],
        rcmIncentive: [],
        lrcmWagers: [],
        lrcmPoly: [],
        lrcmIncentive: [],
        rightRcmMatrix: [],
        rightLrcmMatrix: [],
        tier1ErrorCount: 0,
        tier3WarningCount: 0
    };

    function getVal(id) {
        var el = document.getElementById(id);
        return el ? el.innerText.trim() : "0";
    }

    function cleanNum(txt) {
        if (!txt) return 0;
        var n = parseInt(txt.replace(/[^0-9]/g, ""));
        return isNaN(n) ? 0 : n;
    }

    function isRed(el) {
        if (!el) return false;
        try {
            var style = window.getComputedStyle(el);
            var bg = style.backgroundColor || "";
            var color = style.color || "";
            if (bg.indexOf("255, 0, 0") !== -1 || bg.indexOf("red") !== -1 ||
                color.indexOf("255, 0, 0") !== -1 || color.indexOf("red") !== -1) {
                return true;
            }
        } catch(e) {}
        return false;
    }

    result.rcmUncompletedScore = {
        soccer:     getVal("s_RCM_soccer"),
        basketball: getVal("s_RCM_basketball"),
        outright:   getVal("s_RCM_outright"),
        othersport: getVal("s_RCM_othersport")
    };

    result.lrcmUncompletedScore = {
        soccer:     getVal("s_LRCM_soccer"),
        basketball: getVal("s_LRCM_basketball"),
        outright:   getVal("s_LRCM_outright"),
        othersport: getVal("s_LRCM_othersport")
    };

    function parseSatellite(tdId, wagersOut, polyOut, incOut) {
        var satTd = document.getElementById(tdId);
        if (!satTd) return;
        var tables = satTd.querySelectorAll("table");

        if (tables.length > 0) {
            var rows = tables[0].querySelectorAll("tr");
            for (var r = 0; r < rows.length; r++) {
                var cells = rows[r].querySelectorAll("td, th");
                for (var c = 0; c < cells.length; c += 3) {
                    if (c + 2 < cells.length) {
                        var node = cells[c].innerText.trim();
                        var sport = cells[c+1].innerText.trim();
                        var cntStr = cells[c+2].innerText.trim();
                        var hasRed = isRed(cells[c]) || isRed(cells[c+1]) || isRed(cells[c+2]);

                        if (node && node !== "satellite" && node !== "Uncomplete Wager" && sport) {
                            var cnt = cleanNum(cntStr);
                            var isErr = cnt > 0 || hasRed;
                            if (isErr) result.tier1ErrorCount++;

                            var tag = isErr ? " 🔴[ERROR/Tier 1 积压阻断]" : " [OK/正常]";
                            wagersOut.push(node + " (" + sport + "): " + cntStr + " 单 pending" + tag);
                        }
                    }
                }
            }
        }

        if (tables.length > 1) {
            var rows = tables[1].querySelectorAll("tr");
            for (var r = 0; r < rows.length; r++) {
                var cells = rows[r].querySelectorAll("td, th");
                for (var c = 0; c < cells.length; c += 3) {
                    if (c + 2 < cells.length) {
                        var com = cells[c].innerText.trim();
                        var wager = cells[c+1].innerText.trim();
                        var event = cells[c+2].innerText.trim();
                        var hasRed = isRed(cells[c]) || isRed(cells[c+1]) || isRed(cells[c+2]);

                        if (com && com !== "Com." && com !== "Uncomplete Poly Market") {
                            var wCnt = cleanNum(wager);
                            var eCnt = cleanNum(event);
                            var isWarn = wCnt > 0 || eCnt > 0 || hasRed;
                            if (isWarn) result.tier3WarningCount++;

                            var tag = isWarn ? " 🟡[WARN/Tier 3 仅通知]" : " [OK/正常]";
                            polyOut.push(com + ": Wager=" + wager + ", Event=" + event + tag);
                        }
                    }
                }
            }
        }

        if (tables.length > 2) {
            var rows = tables[2].querySelectorAll("tr");
            for (var r = 0; r < rows.length; r++) {
                var cells = rows[r].querySelectorAll("td, th");
                for (var c = 0; c < cells.length; c += 2) {
                    if (c + 1 < cells.length) {
                        var com = cells[c].innerText.trim();
                        var wager = cells[c+1].innerText.trim();
                        var hasRed = isRed(cells[c]) || isRed(cells[c+1]);

                        if (com && com !== "Com." && com !== "Abnormal Incentive") {
                            var wCnt = cleanNum(wager);
                            var isErr = wCnt > 0 || hasRed;
                            if (isErr) result.tier1ErrorCount++;

                            var tag = isErr ? " 🔴[ERROR/Tier 1 异常阻断]" : " [OK/正常]";
                            incOut.push(com + ": Wager=" + wager + tag);
                        }
                    }
                }
            }
        }
    }

    parseSatellite("s_RCM_satellite", result.rcmWagers, result.rcmPoly, result.rcmIncentive);
    parseSatellite("s_LRCM_satellite", result.lrcmWagers, result.lrcmPoly, result.lrcmIncentive);

    var comps = ["RCM", "LRCM"];
    var games = ["soccer", "basketball", "othersport", "outright"];

    comps.forEach(function(comp) {
        games.forEach(function(game) {
            var mEl = document.getElementById("m_" + comp + "_" + game);
            var aEl = document.getElementById("a_" + comp + "_" + game);
            var annEl = document.getElementById("ann_" + comp + "_" + game);
            var espEl = document.getElementById("esp_" + comp + "_" + game);

            var mVal = mEl ? mEl.innerText.trim() : "0";
            var aVal = aEl ? aEl.innerText.trim() : "0";
            var annVal = annEl ? annEl.innerText.trim() : "0";
            var espVal = espEl ? espEl.innerText.trim() : "0";

            var mCnt = cleanNum(mVal);
            var aCnt = cleanNum(aVal);
            var annCnt = cleanNum(annVal);
            var espCnt = cleanNum(espVal);

            var hasTier3NoMap = mCnt > 0;
            var hasTier1Block = (aCnt > 0 || annCnt > 0 || espCnt > 0);

            if (hasTier1Block) result.tier1ErrorCount++;
            if (hasTier3NoMap) result.tier3WarningCount++;

            var statusTag = " [OK/正常]";
            if (hasTier1Block) {
                statusTag = " 🔴[ERROR/Tier 1 积压阻断]";
            } else if (hasTier3NoMap) {
                statusTag = " 🟡[WARN/Tier 3 NoMap 仅通知]";
            }

            var line = game + ": NoMap=" + mCnt + ", A5Act>120s=" + aCnt + ", Announcement=" + annCnt + ", EventScore>180s=" + espCnt + statusTag;

            if (comp === "RCM") {
                result.rightRcmMatrix.push(line);
            } else {
                result.rightLrcmMatrix.push(line);
            }
        });
    });

    return result;
    """

    res = driver.execute_script(js_code)

    def print_section(title, lines):
        print(f"\n--- {title} ---")
        if not lines:
            print("   * (全部正常 / 0 笔)")
        else:
            for l in lines:
                print(f"   * {l}")

    print("\n" + "#" * 80)
    print(" 🔵 【RCM 全部数据】")
    print("#" * 80)
    print("比分积压:", res["rcmUncompletedScore"])
    print_section("Uncomplete Wagers (卫星未完成注单)", res["rcmWagers"])
    print_section("Uncomplete Poly Market (多元市场)", res["rcmPoly"])
    print_section("Abnormal Incentive (异常激励)", res["rcmIncentive"])

    print("\n" + "#" * 80)
    print(" 🟣 【LRCM 全部数据】")
    print("#" * 80)
    print("比分积压:", res["lrcmUncompletedScore"])
    print_section("Uncomplete Wagers (卫星未完成注单)", res["lrcmWagers"])
    print_section("Uncomplete Poly Market (多元市场)", res["lrcmPoly"])
    print_section("Abnormal Incentive (异常激励)", res["lrcmIncentive"])

    print("\n" + "#" * 80)
    print(" 📊 【右侧 1Plus Mapping 矩阵】")
    print("#" * 80)
    print_section("RCM 规则矩阵", res["rightRcmMatrix"])
    print_section("LRCM 规则矩阵", res["rightLrcmMatrix"])

    print(f"\n[汇总] Tier 1 错误数: {res.get('tier1ErrorCount', 0)}, Tier 3 警告数: {res.get('tier3WarningCount', 0)}")

if __name__ == "__main__":
    main()
