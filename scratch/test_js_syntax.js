const fs = require('fs');

const jsCode = `
var result = {
    categoryName: "RCM",
    dates: [],
    satelliteRows: [],
    rawRows: [],
    totalOkCount: 0,
    errCount: 0,
    resetLogTotal: 0
};

function isRedColor(colStr) {
    if (!colStr) return false;
    var m = colStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
    if (m) {
        var r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
        return (r > 180 && g < 100 && b < 100);
    }
    return false;
}

var sel = typeof document !== 'undefined' ? (document.getElementById("com_select") || document.querySelector("select")) : null;
if (sel && sel.selectedIndex >= 0) {
    result.categoryName = sel.options[sel.selectedIndex].text.trim();
}

var tables = typeof document !== 'undefined' ? document.querySelectorAll("table") : [];
tables.forEach(function(t) {
    if (t.classList.contains("ui-datepicker-calendar") || t.closest(".ui-datepicker") !== null || t.querySelector("table") !== null) return;

    var txt = t.innerText ? t.innerText.trim() : "";
    if (txt.indexOf("Reset Log") === -1 && txt.indexOf("Satellite") === -1) return;

    var dateRegex = /\\b(\\d{1,2}\\/\\d{1,2}(?:\\/\\d{2,4})?)\\b/;
    var foundDates = [];
    var allHeaderRows = t.querySelectorAll("tr");
    for (var rIdx = 0; rIdx < Math.min(allHeaderRows.length, 3); rIdx++) {
        var cells = allHeaderRows[rIdx].querySelectorAll("th, td");
        var rowDates = [];
        cells.forEach(function(c) {
            var cTxt = c.innerText ? c.innerText.trim() : "";
            var m = cTxt.match(dateRegex);
            if (m) {
                rowDates.push(m[1]);
            }
        });
        if (rowDates.length >= 2) {
            foundDates = rowDates;
            break;
        }
    }
    result.dates = foundDates;

    var rows = t.querySelectorAll("tr");
    rows.forEach(function(r) {
        var tds = r.querySelectorAll("td, th");
        if (tds.length < 5) return;

        var txts = [];
        tds.forEach(function(c) { txts.push(c.innerText ? c.innerText.trim() : ""); });

        var sportIdx = txts.indexOf("sport");
        if (sportIdx !== -1 && sportIdx >= 2) {
            var sat = txts[sportIdx - 1];
            var resetLog = txts[sportIdx - 2];
            var dateStartIdx = sportIdx + 1;

            if (sat && sat !== "Satellite" && sat.indexOf("Satellite") === -1) {
                var rCell = tds[sportIdx - 2];
                var rLogNum = parseInt(resetLog) || 0;
                result.resetLogTotal += rLogNum;

                var rBg = rCell ? window.getComputedStyle(rCell).backgroundColor : "";
                var rFg = rCell ? window.getComputedStyle(rCell).color : "";
                var isResetErr = (rLogNum > 0 || isRedColor(rBg) || isRedColor(rFg));

                var rowHasErr = isResetErr;
                var dateItems = [];
                var dateLogStatuses = [];

                var dateCount = foundDates.length > 0 ? foundDates.length : (tds.length - dateStartIdx);
                for (var i = 0; i < dateCount; i++) {
                    var cIdx = dateStartIdx + i;
                    if (cIdx >= tds.length) break;

                    var cell = tds[cIdx];
                    var cellText = cell.innerText ? cell.innerText.trim() : "";
                    var cellLower = cellText.toLowerCase();

                    var cBg = window.getComputedStyle(cell).backgroundColor;
                    var cFg = window.getComputedStyle(cell).color;

                    var isCellErr = false;
                    if (cellLower !== "ok" || isRedColor(cBg) || isRedColor(cFg)) {
                        isCellErr = true;
                        rowHasErr = true;
                        result.errCount++;
                    } else {
                        result.totalOkCount++;
                    }

                    var dHeader = (foundDates && foundDates[i]) ? foundDates[i] : ("Day " + (i + 1));
                    dateItems.push({
                        date: dHeader,
                        text: cellText || "ok",
                        isErr: isCellErr
                    });
                    dateLogStatuses.push(dHeader + ":" + cellText + (isCellErr ? "[Tier 1 报错]" : ""));
                }

                var statusTag = rowHasErr ? "[ERROR/Tier 1]" : " [OK]";
                var logLine = sat + ": Reset Log=" + resetLog + " | " + dateLogStatuses.join(", ") + " " + statusTag;
                result.satelliteRows.push(logLine);

                result.rawRows.push({
                    satellite: sat,
                    resetLog: resetLog,
                    resetLogIsErr: isResetErr,
                    datesData: dateItems,
                    isRowErr: rowHasErr
                });
            }
        }
    });
});
return result;
`;

new Function(jsCode);
console.log("JS syntax is 100% valid!");
