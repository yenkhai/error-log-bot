"""Capture display-only native tables without changing inspection decisions."""
NATIVE_TABLE_SCRIPT = r"""
const output = [];
const mode = typeof arguments[0] === "string" ? arguments[0] : "";
function color(el, property) {
    let current = el;
    while (current) {
        const value = getComputedStyle(current)[property];
        if (value && value !== 'transparent' && value !== 'rgba(0, 0, 0, 0)') return value;
        current = current.parentElement;
    }
    return property === 'color' ? 'rgb(0, 0, 0)' : 'rgb(255, 255, 255)';
}
function rgb(value) {return (value.match(/[\d.]+/g)||[]).map(Number);}
function red(value) {const a=rgb(value);return a.length>=3 && a[0]>=170 && a[1]<=110 && a[2]<=110;}
function cellData(cell) {
    const text = cell.innerText.trim();
    const bg = color(cell,'backgroundColor'), fg = color(cell,'color'), c=rgb(bg);
    const tag = red(bg)||red(fg) ? 'red' : (c.length>=3 && c[0]>=200 && c[1]>=200 && c[2]<=120 ? 'yellow' : (c.length>=3 && c[1]>c[0]+50 && c[1]>c[2]+50 ? 'green' : 'white'));
    return {text:text, bg:tag, css_bg:bg, fg:fg, is_link:!!cell.querySelector('a'), align:getComputedStyle(cell).textAlign};
}
function spans(rows) {
    const result=[],seen=new Set();
    rows.forEach((row,r)=>row.forEach((cell,c)=>{
        if(seen.has(cell))return;seen.add(cell);
        let rs=1,cs=1;
        while(r+rs<rows.length && rows[r+rs][c]===cell)rs++;
        while(c+cs<row.length && row[c+cs]===cell)cs++;
        if(rs>1||cs>1)result.push({row:r,col:c,rowspan:rs,colspan:cs});
    }));
    return result;
}
for(const table of document.querySelectorAll('table')) {
    if(table.closest('.ui-datepicker') || !table.getClientRects().length)continue;
    if(table.closest('#div_checkpoint') || /checkpoint/i.test(table.id))continue;
    const rows=Array.from(table.querySelectorAll('tr')).filter(r=>r.closest('table')===table && !Array.from(r.children).some(c=>c.querySelector('table')));
    if(rows.length<2 || rows.length>2000)continue;
    const heading = rows.slice(0,2).map(r=>r.innerText || Array.from(r.children).map(c=>c.innerText).join(' ')).join(' ').replace(/\s+/g,' ');
    if(mode==='crs' && !(/Agency/i.test(heading) && /API/i.test(heading) && /Credit/i.test(heading)))continue;
    if(mode==='wallet' && !(/Company/i.test(heading) && /Total\s+Pending/i.test(heading)))continue;
    let grid=[];
    rows.forEach((row,ri)=>{
        grid[ri]=grid[ri]||[];let ci=0;
        for(const cell of Array.from(row.children).filter(c=>/^(TD|TH)$/.test(c.tagName))) {
            while(grid[ri][ci])ci++;
            let rs=cell.rowSpan===0?rows.length-ri:Math.max(cell.rowSpan||1,1),cs=Math.max(cell.colSpan||1,1);
            for(let r=ri;r<Math.min(ri+rs,rows.length);r++){
                grid[r]=grid[r]||[];for(let c=ci;c<ci+cs;c++)grid[r][c]=cell;
            }
            ci+=cs;
        }
    });
    const width=Math.max(...grid.map(r=>r.length));
    if(width<2 || width>200)continue;
    // Real CRS/Wallet HTML uses a zero-height row containing only the rowspan
    // label, then starts the data in the following row. Do not invent cells for it.
    grid = grid.filter((logical, index) => {
        const own = Array.from(rows[index].children).filter(c=>/^(TD|TH)$/.test(c.tagName));
        if(!own.length)return false;
        // Collapsed detail/spacer rows must not become bordered blank data rows.
        if(own.every(c=>!c.innerText.trim() && !c.querySelector('img,input,button,select,textarea')))return false;
        const labelOnly = own.length === 1 && own[0].rowSpan > 1;
        const incomplete = Array.from({length:width}, (_,c)=>logical[c]).some(c=>!c);
        return !(labelOnly && incomplete);
    });
    // A decorative short row must not discard an otherwise valid website table.
    for(const row of grid)for(let c=0;c<width;c++)if(!row[c]){
        const blank=document.createElement('td');blank.textContent='';row[c]=blank;
    }
    let hc=0;
    const label=/^(Agency|API|Credit|NIW|Company|Com\.?|Satellite|Hour|Type|Status|IP|Host|No\.?|Remarks|Date|Rpt Complete|Reset Log|Satellite Wager|RPT Punter(?: IP)?|RPT (?:Lg|Agency|Cy|Evt|Pro)|UTC (?:Curr|PL|Odd)|Lg|Ag|Mem|Cy|Evt|Pro|Robot ID|Rpt Date|Function|Game)$/i;
    for(let i=0;i<Math.min(rows.length-1,6);i++){
        const own=Array.from(rows[i].children).filter(c=>/^(TD|TH)$/.test(c.tagName));
        if(!own.length || own.every(c=>!c.innerText.trim() && !c.querySelector('img,input,button,select,textarea')))continue;
        const isHeader=own.some(c=>c.tagName==='TH') || own.some(c=>label.test(c.innerText.trim())) || (own.length===1&&own[0].colSpan>1) || own.every(c=>/^\d{1,2}\/\d{1,2}(?:\/\d{2,4})?$/.test(c.innerText.trim()));
        const isCompanyData=own.some(c=>/^(?:RCM|LRCM|[a-z]{1,4}\d{2,6})$/i.test(c.innerText.trim()));
        const sectionTitle=own.length===1 && own[0].colSpan>1;
        const allHeadings=own.length>0 && own.every(c=>c.tagName==='TH');
        if((isCompanyData && !sectionTitle && !allHeadings) || !isHeader)break;
        hc++;
    }
    if(mode==='crs')hc=1;
    if(mode==='wallet')hc=2;
    if(!hc && mode==='') {
        // CCL Recover is a genuine headerless company/timestamp table.
        const sample=grid.slice(0,5).map(r=>r.map(c=>c.innerText).join(' ')).join(' ');
        const recover=/\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/.test(sample) && /[a-z]{1,4}\d{2,6}/i.test(sample);
        const server=/\bFor\b/.test(sample) && /Running|Idle|Stopped|Die/i.test(sample);
        if(!recover && !server)continue;
    }
    if(hc>=grid.length)continue;
    const headers=grid.slice(0,hc),body=grid.slice(hc);
    if(!body.length)continue;
    const flat=Array.from({length:width},(_,col)=>{
        const seen=new Set(),parts=[];
        for(const row of headers){let c=row[col];if(!seen.has(c)){if(c.innerText.trim())parts.push(c.innerText.trim());seen.add(c);}}
        return parts.join('\n');
    });
    if(!hc)flat.length=0;
    let title='';
    let ancestor=table.parentElement;
    for(let depth=0;ancestor && depth<5;depth++,ancestor=ancestor.parentElement){
        const ips=Array.from(new Set((ancestor.innerText||'').match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g)||[]));
        if(ips.length===1){title=ips[0];break;}
        if(ips.length>1)break;
    }
    const rect=table.getBoundingClientRect();
    output.push({title:title,headers:flat,header_rows:headers.map(r=>r.map(cellData)),header_spans:spans(headers),rows:body.map(r=>r.map(cellData)),cell_spans:spans(body),source:'website',source_x:Math.round(rect.left),source_y:Math.round(rect.top)});
}
return output;
"""


def capture_native_tables(driver, kind=None):
    return driver.execute_script(NATIVE_TABLE_SCRIPT, kind or "")


def prefer_native_tables(stored, tables):
    """Compare coverage, not row counts: native rows may pack several companies."""
    import re
    if not isinstance(tables, list) or not tables:
        return False
    old = stored.get('tables', [])
    def metrics(items):
        ids = set()
        values = 0
        for table in items:
            hidden = set(table.get('derived_status_columns', []))
            for row in table.get('rows', []):
                for index, cell in enumerate(row):
                    if index in hidden:
                        continue
                    text = str(cell.get('text', '') if isinstance(cell, dict) else cell).strip()
                    if text:
                        values += 1
                        ids.update(re.findall(r'(?i)\b[a-z]{1,4}\d{2,6}\b', text))
        return ids, values
    # Preserve robot/server detail tables even when the main matrix is much larger.
    required = set()
    for table in old:
        headers = table.get('headers', [])
        if headers and re.match(r'(?i)^(robot\s*id|ip(?:\s|$)|host$)', str(headers[0])):
            for row in table.get('rows', []):
                if row:
                    first = row[0]
                    value = str(first.get('text', '') if isinstance(first, dict) else first).strip()
                    if value:
                        required.add(value)
    available = set()
    for table in tables:
        available.add(str(table.get('title', '')).strip())
        for row in table.get('rows', []):
            for cell in row:
                available.add(str(cell.get('text', '') if isinstance(cell, dict) else cell).strip())
    if not required.issubset(available):
        return False
    old_ids, old_values = metrics(old)
    new_ids, new_values = metrics(tables)
    if old_ids:
        return old_ids.issubset(new_ids) and new_values >= old_values * .65
    return sum(len(t.get('rows', [])) for t in tables) >= sum(len(t.get('rows', [])) for t in old)


def forecast_right_tables(tables):
    """Forecast's right comparison table is identified by its Remark column."""
    return [table for table in tables if any(str(header).strip().lower() == 'remark' for header in table.get('headers', []))]
