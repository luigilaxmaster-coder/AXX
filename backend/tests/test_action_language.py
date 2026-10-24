import unittest
from unittest.mock import patch
from backend.actions.desktop import resolve_desktop

class ActionLanguageTests(unittest.TestCase):
    def test_compound_and_conversational_search(self):
        cases={
            'abre youtube y buscame un video de gatitos':('youtube','un video de gatitos'),
            '/search youtube afraid':('youtube','afraid'),
            'busca afraid':('google','afraid'),
            'ponme afraid the theneihborrhod':('youtube','afraid the theneihborrhod'),
            'reproduce una canción de The Neighbourhood':('youtube','una canción de The Neighbourhood'),
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

if __name__=='__main__':unittest.main()
