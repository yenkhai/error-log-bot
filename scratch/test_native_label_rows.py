import unittest,subprocess,json,shutil
from core.native_tables import NATIVE_TABLE_SCRIPT

@unittest.skipUnless(shutil.which('node'),'Node required for DOM fixture')
class NativeStructuralRows(unittest.TestCase):
    def test_real_crs_structure_does_not_add_blank_rows(self):
        harness=r'''
let input='';process.stdin.on('data',d=>input+=d);process.stdin.on('end',()=>{
const script=JSON.parse(input);
function c(text,rs=1,cs=1){return {innerText:text,tagName:'TD',rowSpan:rs,colSpan:cs,parentElement:null,querySelector:()=>null,style:{backgroundColor:'rgb(255, 255, 255)',color:'rgb(0, 0, 0)',textAlign:'left'}}}
let t={id:'',closest:()=>null,getClientRects:()=>[{}],getBoundingClientRect:()=>({left:0,top:0})};
const rr=cells=>({children:cells,innerText:cells.map(c=>c.innerText).join(' '),closest:()=>t});
let rows=[rr([c('Agency'),c('API',1,2),c('Credit',1,2)]),rr([c('nv01',4)]),rr([c('date1'),c('ok'),c('credit1'),c('ok')]),rr([c('date2'),c('ok'),c('-',1,2)]),rr([c('date3'),c('ok'),c('-',1,2)])];
t.querySelectorAll=()=>rows;
const document={querySelectorAll:()=>[t],createElement:()=>c('')};const style=e=>e.style;
const result=new Function('document','getComputedStyle','script','return (function(){return eval(script)}).call(null,"crs")')(document,style,'(function(){'+script+'}).call(null,"crs")');
if(result.length!==1||result[0].rows.length!==3||result[0].rows[0][0].text!=='nv01')throw Error('label-only row became data');
if(!result[0].cell_spans.some(s=>s.rowspan===3))throw Error('agency merge incorrect');
});
'''
        result=subprocess.run(['node','-e',harness],input=json.dumps(NATIVE_TABLE_SCRIPT),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
