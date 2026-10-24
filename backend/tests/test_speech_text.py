import unittest

from backend.speech.speech_text import prepare_spoken_text, spanish_integer


class SpokenTextTests(unittest.TestCase):
    def test_spanish_accents_questions_and_voice_name_survive(self):
        text = '¡Hola! Soy Axx Titán. ¿Cómo estás? Mañana te ayudaré.'
        self.assertEqual(prepare_spoken_text(text, 'es-DO'), (text, 'es'))
        self.assertEqual(prepare_spoken_text('Man\u0303ana', 'es')[0], 'Mañana.')

    def test_cardinals_and_abbreviations_are_spoken_in_spanish(self):
        self.assertEqual(prepare_spoken_text('Sr. Pérez, hay 22 tareas y 75% listo', 'es')[0],
                         'señor Pérez, hay veintidós tareas y setenta y cinco por ciento listo.')
        for number, expected in [(100, 'cien'), (101, 'ciento uno'), (500, 'quinientos'),
                                 (999, 'novecientos noventa y nueve'), (2026, 'dos mil veintiséis')]:
            self.assertEqual(spanish_integer(number), expected)

    def test_identifiers_versions_dates_and_decimals_are_not_rewritten(self):
        text = 'v0.20.19 192.168.1.1 23/10/2026 09:30 -25 3,14 0012 X123 99999.'
        self.assertEqual(prepare_spoken_text(text, 'es')[0], text)

    def test_latin_punctuation_does_not_become_chinese(self):
        self.assertEqual(prepare_spoken_text('**Sí**... vamos — juntos!!', 'es')[0], 'Sí, vamos, juntos!')
        self.assertEqual(prepare_spoken_text('Ready', 'en-US')[0], 'Ready.')
        self.assertEqual(prepare_spoken_text('Hay 2 tareas')[0], 'Hay 2 tareas.')  # ambiguous: no forced language
        self.assertEqual(prepare_spoken_text('Hola, hay 2 tareas')[0], 'Hola, hay dos tareas.')

    def test_english_and_other_languages_do_not_receive_spanish_expansions(self):
        self.assertEqual(prepare_spoken_text('Dr. Smith has 22 tasks.', 'en')[0], 'Dr. Smith has 22 tasks.')
        self.assertEqual(prepare_spoken_text('Bonjour', 'fr'), ('Bonjour', 'fr'))

    def test_conversational_pauses_ordinals_and_technical_terms(self):
        text = 'Hola principal podemos revisar el PDF de la 1ª prueba'
        self.assertEqual(prepare_spoken_text(text, 'es')[0],
                         'Hola principal, podemos revisar el pe-de-efe de la primera prueba.')
        text2 = 'Por supuesto revisa la pág. 10 y el Wi-Fi'
        self.assertEqual(prepare_spoken_text(text2, 'es')[0],
                         'Por supuesto, revisa la página diez y el uay-fay.')
        self.assertEqual(prepare_spoken_text('1er intento, 2do intento y 3er intento.', 'es')[0],
                         'primer intento, segundo intento y tercer intento.')


if __name__ == '__main__':
    unittest.main()
