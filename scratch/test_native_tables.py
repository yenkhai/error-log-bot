import unittest
import tkinter as tk
from core.native_tables import prefer_native_tables
from core.checkpoint_store import CheckpointStore
from gui.tab_log_viewer import LogViewerTab, LogDetailWindow


def cell(text,bg='rgb(200, 215, 166)'):
    return {'text':text,'bg':'white','css_bg':bg,'fg':'black'}


class NativeTableTests(unittest.TestCase):
    def test_partial_capture_keeps_full_aggregate(self):
        self.assertFalse(prefer_native_tables({'tables':[{'rows':[[1]]*32}]},[{'rows':[[1]]*2}]))

    def test_empty_capture_keeps_existing_data(self):
        self.assertFalse(prefer_native_tables({'tables':[]},[]))

    def test_full_matrix_can_replace_summary(self):
        self.assertTrue(prefer_native_tables({'tables':[{'rows':[[1]]*24}]},[{'rows':[[1,2,3]]*24}]))

    def test_packed_company_rows_are_complete(self):
        old={'tables':[{'headers':['Company','Pending','Status'],'derived_status_columns':[2],
             'rows':[['d0005','0','OK'],['d0008','0','OK'],['d0009','0','OK']]}]}
        packed=[{'rows':[['d0005','0','d0008','0','d0009','0']]}]
        self.assertTrue(prefer_native_tables(old,packed))

    def test_missing_company_is_not_complete(self):
        old={'tables':[{'rows':[['d0005','0'],['d0008','0']]}]}
        self.assertFalse(prefer_native_tables(old,[{'rows':[['d0005','0','0','0','0']]}]))

    def test_missing_robot_detail_must_not_be_discarded(self):
        old={'tables':[{'headers':['Robot ID','Details'],'rows':[['998','robot detail']]}]}
        self.assertFalse(prefer_native_tables(old,[{'rows':[['d0005','ok'],['d0008','ok']]}]))

    def test_multirow_headers_merged_cells_and_horizontal_layout(self):
        root=tk.Tk();root.withdraw()
        try:
            table={'source':'website','source_x':0,'source_y':0,'headers':['Satellite','15/10/2026\nWager','15/10/2026\nPunter'],
                'header_rows':[[cell('Satellite'),cell('15/10/2026'),cell('15/10/2026')],[cell('Satellite'),cell('Wager'),cell('Punter')]],
                'header_spans':[{'row':0,'col':0,'rowspan':2,'colspan':1},{'row':0,'col':1,'rowspan':1,'colspan':2}],
                'rows':[[cell('d0005'),cell('ok','rgb(0, 208, 0)'),cell('ok','rgb(0, 208, 0)')]]}
            second={**table,'source_x':500}
            CheckpointStore.save('niw_08','RPT AI',True,tables=[table,second])
            tab=LogViewerTab(root,None)
            win=LogDetailWindow(tab,7);win.update()
            frames=win.table_frame.winfo_children()
            self.assertEqual(len(frames),2)
            self.assertEqual(frames[0].winfo_y(),frames[1].winfo_y())
            self.assertGreater(frames[1].winfo_x(),frames[0].winfo_x())
            children=frames[0].winfo_children()
            headers=[c for c in children if c.cget('text')=='15/10/2026']
            self.assertEqual(len(headers),1)
            self.assertEqual(int(headers[0].grid_info()['columnspan']),2)
            self.assertTrue(any(c.cget('bg')=='#00d000' for c in children))
            for timer in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", timer)
            win.destroy()
        finally:
            root.destroy()


if __name__=='__main__':
    unittest.main()
