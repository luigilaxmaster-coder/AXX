"""Regression contract for the reported dialogue; native acceptance is separate."""
from contextlib import nullcontext
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch

from backend.actions.desktop import resolve_desktop
from backend.actions.browser_tasks import select_video, player_position
from backend.actions.application_tools import ApplicationTool
from backend.actions.tools import ToolResult
from backend.mobile.control import AutomationLease


class BrowserTaskTests(unittest.TestCase):
    def test_reported_dialogue_and_object_routing(self):
        context = {'engine':'youtube','query':'Faint de Linkin Park'}
        cases = {
            'abre chrome y busca youtube': ('axx.app.browse', {'application':'chrome','url':'https://www.youtube.com/'}),
            'pon el mouse sobre geist en chrome': ('axx.app.hover', {'application':'chrome','name':'geist'}),
            'busca en yotune una cncion la cancion faint de linkin park': ('axx.desktop.search', {'engine':'youtube','query':'faint de linkin park'}),
            'reproducela': ('axx.app.youtube', {'application':'chrome','query':'Faint de Linkin Park'}),
            'reprodúcela': ('axx.app.youtube', {'application':'chrome','query':'Faint de Linkin Park'}),
            'reproduce la cancion': ('axx.app.youtube', {'application':'chrome','query':'Faint de Linkin Park'}),
            'reproduce la cancion de linkin park faint en yotube': ('axx.app.youtube', {'application':'chrome','query':'linkin park faint'}),
        }
        for source in ('text','voice'):
            for text, (command, inputs) in cases.items():
                with self.subTest(text=text, source=source):
                    result = resolve_desktop(text, source, context)
                    self.assertEqual(result['command_id'], command)
                    self.assertEqual(result['inputs'], inputs)
        for text in ('pon la capa en rojo','pon el volumen al 30','no reproduzcas Faint','"reproduce Faint"'):
            self.assertIsNone(resolve_desktop(text,'text'))
        for text in ('reproducela','reproduce la cancion'):
            self.assertEqual(resolve_desktop(text,'text')['match'],'needs_input')
        for text in ('ponme afraid the theneihborrhod','reproduce una canción de The Neighbourhood'):
            self.assertEqual(resolve_desktop(text,'text')['command_id'],'axx.app.youtube')

    def test_chrome_context_preserves_the_browser_and_literal_query(self):
        result = resolve_desktop('busca Faint en YouTube','text',{'application':'chrome'})
        self.assertEqual(result['inputs'], {'application':'chrome','url':'https://www.youtube.com/results?search_query=Faint'})

    def test_video_identity_and_ambiguity(self):
        video = {'title':'Faint [Official Music Video] - Linkin Park','video_id':'a'*11,'url':'https://www.youtube.com/watch?v='+'a'*11}
        cover = dict(video, title='Faint Linkin Park cover', video_id='b'*11)
        self.assertEqual(select_video([cover,video], 'Faint de Linkin Park'), video)
        self.assertEqual(select_video([video], 'LinkinPark Faint'), video)
        for rows in ([], [video,dict(video,video_id='c'*11)]):
            with self.assertRaises(ValueError):select_video(rows,'Faint Linkin Park')
        with self.assertRaises(ValueError): select_video([video],'Numb Linkin Park')

    def test_player_requires_progress_control_and_pause_state(self):
        slider = {'control_type':'ControlType.Slider','name':'Barra de progreso','state':{'RangeValue':{'value':5}}}
        pause = {'control_type':'ControlType.Button','name':'Pausa (k)'}
        self.assertEqual(player_position({'controls':[slider,pause]}),5)
        self.assertIsNone(player_position({'controls':[slider]}))
        self.assertIsNone(player_position({'controls':[slider,slider,pause]}))
        self.assertIsNone(player_position({'controls':[slider,pause],'truncated':True}))
        self.assertIsNone(player_position({'controls':[slider,pause,{'name':'Anuncio 1 de 2'}]}))

    def test_youtube_workflow_requires_two_advancing_samples_and_current_title(self):
        window = {'window_id':10,'pid':20,'title':'initial','process_started':'one'}
        video = {'title':'Faint - Linkin Park','video_id':'a'*11,'url':'https://www.youtube.com/watch?v='+'a'*11}
        def player(value):
            return {'window_title':'Faint - Linkin Park - YouTube - Google Chrome','controls':[
                {'control_type':'ControlType.Slider','name':'Barra de progreso','state':{'RangeValue':{'value':value}}},
                {'control_type':'ControlType.Button','name':'Pausa (k)'}]}
        snapshots = [{'links':[video]},player(3),player(4)]
        control = SimpleNamespace(renew=lambda:None,is_set=lambda:False,wait=lambda seconds:False)
        runtime = SimpleNamespace(input_control=SimpleNamespace(automation=lambda cancelled:nullcontext(control)))
        tool=ApplicationTool('youtube')
        profile={'commands':[{'kind':'navigate','names':['Address and search bar']}]}
        with patch('backend.actions.application_tools._window_rows',return_value=(profile,[window])), \
             patch('backend.actions.application_tools._select_window',return_value=(profile,window)), \
             patch('backend.actions.application_tools._observe',return_value={}), \
             patch('backend.actions.windows_automation.focus_window'), \
             patch('backend.actions.windows_automation.read_window_content',side_effect=snapshots), \
             patch.object(tool,'_navigate_url',return_value=ToolResult(True)) as navigate:
            result=tool.execute_with_runtime({'application':'chrome','query':'Faint Linkin Park'},None,threading.Event(),runtime)
        self.assertTrue(result.success,result.error)
        self.assertTrue(tool.verify_postconditions({},result)[0])
        self.assertEqual([result.output['position_before'],result.output['position_after']],[3,4])
        self.assertEqual(navigate.call_args.args[0]['url'],video['url'])

    def test_hover_reobserves_and_rejects_incomplete_or_duplicate_labels(self):
        window = {'window_id':10,'pid':20,'title':'Owned fixture','process_started':'one'}
        item = {'name':'Geist','enabled':True,'bounds':{'x':100,'y':200,'width':40,'height':20}}
        control = SimpleNamespace(renew=lambda:None)
        runtime = SimpleNamespace(input_control=SimpleNamespace(automation=lambda cancelled:nullcontext(control)))
        tool = ApplicationTool('hover')
        for controls,truncated,valid in (([item],False,True),([item,item],False,False),([item],True,False)):
            with self.subTest(valid=valid), \
                 patch('backend.actions.application_tools._window_rows',return_value=(None,[window])), \
                 patch('backend.actions.application_tools._select_window',return_value=(None,window)), \
                 patch('backend.actions.windows_automation.focus_window'), \
                 patch('backend.actions.windows_automation.read_window_content',return_value={'controls':controls,'truncated':truncated}), \
                 patch('backend.actions.application_tools._input',return_value={'success':True,'output':{'confirmed':True},'evidence':{'verification':'cursor_readback'}}) as move:
                result = tool.execute_with_runtime({'application':'chrome','name':'Geist'},None,threading.Event(),runtime)
                self.assertEqual(result.success,valid)
                self.assertEqual(move.call_count,int(valid))
                if valid:self.assertEqual(move.call_args.kwargs,{'x':120,'y':210})

    def test_no_playback_receipt_from_handoff_or_paused_player(self):
        tool = ApplicationTool('youtube')
        for result in (ToolResult(True,evidence={'verification':'os_handoff'}),ToolResult(False)):
            self.assertFalse(tool.verify_postconditions({},result)[0])

    def test_renew_never_revives_a_cancelled_lease(self):
        native = SimpleNamespace(abort=threading.Event(),lease='one',renew=lambda *args:self.fail('renewed cancelled lease'))
        cancelled=threading.Event();cancelled.set()
        with self.assertRaises(ValueError):AutomationLease(native,'one',cancelled).renew()


if __name__ == '__main__':unittest.main()
