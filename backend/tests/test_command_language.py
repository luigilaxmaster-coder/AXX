"""Command outcomes for Spanish paraphrases, ASR errors and protected payloads."""
import unittest
from unittest.mock import patch

from backend.actions.command_language import command_text
from backend.actions.desktop import resolve_desktop


OPEN_REQUESTS = (
    '¿Me puedes abrir Obsidian?',
    'Oye Axx, por favor podrías abrirme Obsidian',
    'Necesito que me abras Obsidian',
    'Quiero abrir Obsidian',
    'Me gustaría abrir Obsidian',
    'Ábreme la aplicación de Obsidian',
    'Lanza Obsidian',
    'Arranca Obsidian',
    'Habre Obsidian',
    'Avre. Obsidian',
    'Abre mi obsedia',
    'Oye, Axx, ¿podrías, por favor, abrirme Obsidian?',
    'Quisiera abrir Obsidian',
)
SEARCH_REQUESTS = (
    '¿Me podrías buscar Árboles azules en YouTube?',
    'Necesito que busques Árboles azules en YouTube',
    'Quiero buscar Árboles azules usando YouTube',
    'Me gustaría buscar Árboles azules con YouTube',
    'En YouTube búscame Árboles azules',
    'Oye Axx, en you tube busca Árboles azules',
    'Bosca Árboles azules en YouTube',
    'Busca en yutube Árboles azules',
    'Encuentra Árboles azules en YouTube',
    'En YouTube encuentra Árboles azules',
)


class CommandLanguageTests(unittest.TestCase):
    def test_open_variants_resolve_the_observed_app(self):
        with patch('backend.actions.windows_apps.installed_apps', return_value=[{'name':'Obsidian','app_id':'md.obsidian'}]):
            for phrase in OPEN_REQUESTS:
                with self.subTest(phrase=phrase):
                    result=resolve_desktop(phrase,'voice')
                    self.assertEqual(result.get('command_id'),'axx.desktop.installed_app')
                    self.assertEqual(result['inputs'],{'app_id':'md.obsidian'})

    def test_search_variants_keep_query_and_destination(self):
        for phrase in SEARCH_REQUESTS:
            with self.subTest(phrase=phrase):
                result=resolve_desktop(phrase,'voice')
                self.assertEqual(result.get('command_id'),'axx.desktop.search')
                self.assertEqual(result['inputs'],{'engine':'youtube','query':'Árboles azules'})
        for phrase in ('busca Árboles azules en Chrome','en Google Chrome, búscame Árboles azules',
                       'And Chrome. Bosca Árboles azules','me puedes buscar Árboles azules usando Chrome'):
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_desktop(phrase,'voice')['inputs'],{'application':'chrome','url':'https://www.google.com/search?q=%C3%81rboles+azules'})

    def test_music_desire_and_app_alias_never_switch_to_youtube(self):
        for phrase in ('Quiero escuchar Bachata Rosa en Spotify','Reprogoce Bachata Rosa en Spotify',
                       'reproduce Bachata Rosa en espotifai'):
            with self.subTest(phrase=phrase):
                result=resolve_desktop(phrase,'voice')
                self.assertEqual(result['inputs'],{'url':'https://open.spotify.com/search/Bachata%20Rosa'})
        self.assertEqual(resolve_desktop('quiero escuchar espotifai','voice')['command_id'],'axx.desktop.spotify.play')

    def test_close_and_focus_keep_observed_identity(self):
        row={'window_id':18,'pid':45,'title':'Spotify Premium'}
        with patch('backend.actions.windows_automation.list_windows',return_value=[row]), \
             patch('backend.actions.windows_automation.process_name',return_value='spotify.exe'):
            self.assertEqual(resolve_desktop('necesito que cierres Spotify','voice')['inputs'],{'window_id':'12','pid':45})
            self.assertEqual(resolve_desktop('me puedes enfocar Spotify','voice')['command_id'],'axx.desktop.window.focus')
        self.assertEqual(resolve_desktop('puedes moverme el mouse a 100 y 200','voice')['inputs'],{'x':100,'y':200})

    def test_negated_quoted_informational_and_unrelated_requests_do_not_become_actions(self):
        phrases=('No abras Spotify','Quiero que no cierres Spotify','¿Cómo puedo abrir Spotify?',
                 'Explícame cómo buscar en YouTube','Di abre Spotify','"abre Spotify"',
                 'Me gustaría saber cómo abrir Spotify','Abro Spotify todos los días',
                 'No, abre Spotify','Nunca cierres Spotify','Quiero que escribas un poema')
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                result=resolve_desktop(phrase,'voice')
                self.assertFalse(result and result.get('match')=='exact')

    def test_payloads_and_typed_scripts_remain_literal(self):
        for phrase in ('/cmd echo Axx & echo BOSCA','ejecuta en cmd: echo Me puedes abrir Spotify',
                       '/comando axx.artifact.write {"content":"habre"}',
                       'escribe en ChatGPT No cierres Spotify; di "Bosca".',
                       'pega en Antigravity Axx /cmd echo $HOME',
                       'escribe en ChatGPT por favor'):
            self.assertEqual(command_text(phrase,'voice'),phrase)
        result=resolve_desktop('busca "Bosca" & MiArchivo.PDF en Google','voice')
        self.assertEqual(result['inputs']['query'],'"Bosca" & MiArchivo.PDF')
        result=resolve_desktop('abre https://Example.com/Case?Q=Bosca','voice')
        self.assertEqual(result['inputs']['url'],'https://Example.com/Case?Q=Bosca')
        self.assertEqual(resolve_desktop('busca por favor','voice')['inputs']['query'],'por favor')

    def test_voice_corrections_are_source_bound_and_normalization_is_idempotent(self):
        self.assertEqual(command_text('Bosca gatos','text'),'Bosca gatos')
        for phrase in (*OPEN_REQUESTS,*SEARCH_REQUESTS):
            canonical=command_text(phrase,'voice')
            self.assertEqual(command_text(canonical,'voice'),canonical)
        self.assertEqual(resolve_desktop('por favor en Chrome busca','voice')['match'],'needs_input')

    def test_similar_observed_apps_stay_ambiguous(self):
        with patch('backend.actions.windows_apps.installed_apps',return_value=[
                {'name':'Notepad','app_id':'one'},{'name':'NotepadX','app_id':'two'}]):
            result=resolve_desktop('abre notepadd','voice')
            self.assertEqual(result['match'],'ambiguous')
            self.assertEqual(len(result['candidates']),2)

