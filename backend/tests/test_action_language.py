import unittest
import subprocess
from unittest.mock import patch
from backend.actions.desktop import resolve_desktop
from backend.actions import windows_apps

class ActionLanguageTests(unittest.TestCase):
    def test_compound_and_conversational_search(self):
        cases={
            'abre youtube y buscame un video de gatitos':('youtube','un video de gatitos'),
            '/search youtube afraid':('youtube','afraid'),
            'busca afraid':('google','afraid'),
            'puedes buscar en youtube vídeos de gatos':('youtube','vídeos de gatos'),
            'abre Google y busca conversión de unidades':('google','conversión de unidades'),
        }
        for text,(engine,query) in cases.items():
            with self.subTest(text=text):
                r=resolve_desktop(text,'text')
                self.assertIsNotNone(r)
                self.assertEqual(r.get('command_id'),'axx.desktop.search')
                self.assertEqual(r['inputs'],{'engine':engine,'query':query})

    def test_search_context_and_followup(self):
        context={'engine':'youtube','query':'afraid','url':'https://www.youtube.com/results?search_query=afraid'}
        self.assertEqual(resolve_desktop('busca gatitos','text',context)['inputs']['engine'],'youtube')
        self.assertEqual(resolve_desktop('pero abrela en el navegador','text',context)['inputs']['query'],'afraid')
        self.assertNotEqual(resolve_desktop('sí','text',context).get('match'),'exact')

    def test_quoted_negative_and_incomplete_do_not_execute(self):
        for text in ('no busques afraid','cómo buscar en youtube','explica /search youtube afraid','"abre youtube"','abre youtube y borra archivos'):
            r=resolve_desktop(text,'text')
            self.assertFalse(r and r.get('match')=='exact',text)
        for text in ('/search youtube','busca','ponme'):
            r=resolve_desktop(text,'text')
            self.assertEqual(r['match'],'needs_input')

    def test_voice_music_and_observed_app_names(self):
        for phrase in ('búscame una música de Juan Luis Guerra', 'busca canción de Juan Luis Guerra'):
            self.assertEqual(resolve_desktop(phrase,'voice')['inputs'],
                             {'engine':'youtube','query':'Juan Luis Guerra'})
        apps=[{'name':'Obsidian','app_id':'md.obsidian'}, {'name':'Spotify','app_id':'spotify.observed'}]
        with patch('backend.actions.windows_apps.installed_apps',return_value=apps):
            self.assertEqual(resolve_desktop('abre mi obsedia','voice')['inputs'],{'app_id':'md.obsidian'})
            self.assertEqual(resolve_desktop('abre Spotify','voice')['inputs'],{'app_id':'spotify.observed'})
            self.assertEqual(resolve_desktop('busca Obsidian en mi escritorio y ábrelo','voice')['inputs'],{'app_id':'md.obsidian'})
            self.assertFalse(resolve_desktop('abre app desconocida','voice').get('match')=='exact')
            self.assertEqual(resolve_desktop('busca informe.pdf en mi escritorio y ábrelo','voice')['match'],'unsupported')

    def test_recent_spoken_commands_keep_the_requested_destination(self):
        self.assertEqual(resolve_desktop('abre yotube','voice')['inputs'],{'url':'https://www.youtube.com/'})
        self.assertEqual(resolve_desktop('en chrome busca youtube','voice')['inputs'],{'application':'chrome','url':'https://www.google.com/search?q=youtube'})
        self.assertEqual(resolve_desktop('And Chrome. Busca YouTube.','voice')['inputs'],{'application':'chrome','url':'https://www.google.com/search?q=YouTube'})
        self.assertIsNone(resolve_desktop('And Chrome. Busca YouTube.','text'))
        self.assertEqual(resolve_desktop('En Chrome Bosca YouTube.','voice')['inputs'],{'application':'chrome','url':'https://www.google.com/search?q=YouTube'})
        self.assertIsNone(resolve_desktop('En Chrome Bosca YouTube.','text'))
        self.assertEqual(resolve_desktop('busca en Chrome Obsidian','voice')['inputs'],{'application':'chrome','url':'https://www.google.com/search?q=Obsidian'})
        result=resolve_desktop('ponme en spotify faint de linkinpark','voice')
        self.assertEqual(result['command_id'],'axx.desktop.open_url')
        self.assertEqual(result['inputs']['url'],'https://open.spotify.com/search/faint%20de%20linkinpark')
        self.assertNotEqual(resolve_desktop('ponme Spotify algo más en YouTube','voice').get('command_id'),'axx.desktop.search')

    def test_windows_inventory_uses_last_observed_apps_after_timeout(self):
        observed=[{'name':'Obsidian','app_id':'md.obsidian'}]
        with patch.object(windows_apps,'_cache',observed), patch.object(windows_apps,'_updated',0), \
             patch.object(windows_apps.subprocess,'run',side_effect=subprocess.TimeoutExpired('Get-StartApps',12)) as launch:
            self.assertEqual(windows_apps.installed_apps(refresh=True),observed)
            self.assertEqual(windows_apps.find_app('obsidian',lambda value:value.casefold()),observed)
            self.assertEqual(launch.call_count,1)

if __name__=='__main__':unittest.main()
