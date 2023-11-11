# импорт библиотек
import pathlib
import sys
import time
from typing import Optional

import requests
from PyQt5 import QtWidgets
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import *


class PdfExportWorker(QObject):
    complete = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, inn: str, target_folder: str):
        super().__init__()
        self.target_folder = target_folder
        self.inn = inn

    def run(self):
        search_response = requests.post(
            'https://egrul.nalog.ru/', data={
                'vyp3CaptchaToken': '',
                'page': '',
                'query': self.inn,
                'region': '',
                'PreventChromeAutocomplete': '',
            }
        )
        search_token = search_response.json()['t']  # получение токена пользователя для обхода системы защиты
        timestamp = int(
            time.time() * 1000
        )  # для получения pdf используется время, так что эта переменная просто хранит время для отправки следующего запроса
        search_result_response = requests.get(
            f'https://egrul.nalog.ru/search-result/{search_token}',
            params={'r': timestamp, '_': timestamp}
        )  # отправка запроса на создание pdf файла

        first_result_token = search_result_response.json()['rows'][0]['t']
        first_result_name = search_result_response.json()['rows'][0]['n']

        timestamp = int(time.time() * 1000)  # очередной замер времени
        generate_pdf_ask = requests.get(
            f'https://egrul.nalog.ru/vyp-request/{first_result_token}',
            params={'_': timestamp}
        )  # ещё один запрос

        def is_pdf_ready() -> bool:  # функция для проверки готовности pdf файла на скачивание и возвращение параметра готовности
            timestamp = int(time.time() * 1000)
            generate_pdf_status = requests.get(
                f'https://egrul.nalog.ru/vyp-status/{first_result_token}',
                params={'r': timestamp, '_': timestamp}
            )  # проверка готовности файла по средством запросов
            return generate_pdf_status.json()['status'] == 'ready'

        while not is_pdf_ready():  # запуск цикла проверки готовности pdf файла
            print('Ожидаем генерации отчёта')
            time.sleep(1)

        pdf_report = requests.get(
            f'https://egrul.nalog.ru/vyp-download/{first_result_token}'
        )  # запрос на возврат pdf

        result_filename = f'Выписка из ЕГРИП по {first_result_name}.pdf'.replace(
            '"',
            ''
        )  # переименовывание файла pdf

        with (pathlib.Path(self.target_folder) / result_filename).open('wb') as result_file:
            result_file.write(pdf_report.content)  # создаёт файл и  сохраняет в дирректорию reports

        self.complete.emit(result_filename)
        self.finished.emit()


class InnSearchWindow(QMainWindow):  # инициализация GUI окна

    def __init__(self):
        super().__init__()  # наследование элементов родительного класса

        self.setWindowTitle('ИНН парсер')  # установка названия UI
        self.setGeometry(450, 170, 690, 245)  # установка размера UI

        self.inn_input = QtWidgets.QLineEdit(self)  # создание объекта поля ввода ИНН
        self.inn_input.setGeometry(50, 100, 270, 25)  # установка размеров поля ввода ИНН
        self.inn_input.move(10, 20)  # перемещение объекта поля ввода по GUI

        self.button_find_inf = QtWidgets.QPushButton(self)  # создание обьекта кнопки1
        self.button_find_inf.move(10, 50)  # перемещение кнопки1
        self.button_find_inf.setText('Найти информацию')  # установка надписи кнопки1
        self.button_find_inf.adjustSize()  # автоматический подгон размеров кнопки1 под текст установленный в ней
        self.button_find_inf.clicked.connect(
            self.parser
        )  # привязка действия cliked() (которая считывает нажатие кнопки) над кнопкой к функции parser()

        self.button_save_min_inf = QtWidgets.QPushButton(
            self
        )  # всё аналогично кнопке 1 за исключением того что кнопка передвигается за пределы окна GUI
        self.button_save_min_inf.move(1000, 1000)
        self.button_save_min_inf.setText('Сохранить краткую информацию')
        self.button_save_min_inf.adjustSize()
        self.button_save_min_inf.clicked.connect(self.save_txt)

        self.button_save_full_inf = QtWidgets.QPushButton(
            self
        )  # всё аналогично кнопке 1 за исключением того что кнопка передвигается за пределы окна GUI
        self.button_save_full_inf.move(1000, 1000)
        self.button_save_full_inf.setText('Скачать полную информацию')
        self.button_save_full_inf.adjustSize()
        self.button_save_full_inf.clicked.connect(self.start_pdf_report_download_background)

        self.button_delete_inf = QtWidgets.QPushButton(self)
        self.button_delete_inf.move(1000, 1000)
        self.button_delete_inf.setText('удалить данные')
        self.button_delete_inf.adjustSize()
        self.button_delete_inf.clicked.connect(self.del_inf)

        self.textwindow = QtWidgets.QLabel(self)  # создание текстового окна
        self.textwindow.move(10, 130)  # перемещение текстового окна

        self.active_background_thread: Optional[QThread] = None
        self.export_worker: Optional[PdfExportWorker] = None

    def parser(self):  # функция отвечающая за парсинг введённого ИНН
        self.inn = self.inn_input.text()  # считывание значения из окна ввода ИНН (для удобности дальнейшего использования заносится в отдельную переменную)
        if self.inn.isdigit():  # проверка правильности введённого ИНН, а именно чтоб ИНН состоял из 10 или 12 символов
            respons1 = requests.post(
                'https://egrul.nalog.ru/',
                {'query': self.inn}
            )  # отправка запроса с введённым ИНН, и запись ответа
            wtf = respons1.text.split('"')[
                3]  # ответ приходет в нечетабильном и в то же время странном виде, поэтому его разбивает и вытаскивает часть ссылки для следёющего запроса
            respons2 = requests.get(
                'https://egrul.nalog.ru/search-result/' + wtf
            )  # отправка второго запроса, ну и аналогично получение ответа
            if len(respons2.json()['rows']) > 0:
                json_data = respons2.json()['rows'][0]
                if len(json_data) == 14:
                    text_string = json_data['a'] + '\n' + json_data['g'] + '\n' + json_data['n'] + '\nИНН: ' + \
                                  json_data['i'] + '\nОГРН: ' + json_data['o'] + '\nДата присвоения ОГРН: ' + \
                                  json_data['r'] + '\nКПП: ' + json_data['p']
                    self.textwindow.setText(text_string)
                    self.textwindow.adjustSize()
                    self.button_save_full_inf.move(
                        10,
                        100
                    )  # только после того как была выведена краткая информация будут перемещены в пределы окна GUI кнопка1 и кнопка2
                    self.button_save_min_inf.move(10, 75)
                    self.button_delete_inf.move(280, 20)
                else:
                    text_string = f"{json_data['n']}\nОГРНИП: {json_data['o']}\nИНН: {json_data['i']}\nДата присвоения ОГРНИП: {json_data['r']}"
                    self.textwindow.setText(text_string)
                    self.textwindow.adjustSize()
                    self.button_save_full_inf.move(
                        10,
                        100
                    )  # только после того как была выведена краткая информация будут перемещены в пределы окна GUI кнопка1 и кнопка2
                    self.button_save_min_inf.move(10, 75)
                    self.button_delete_inf.move(280, 20)
            else:
                self.textwindow.setText("Такого ИНН не существует")
                self.textwindow.adjustSize()
        else:
            self.textwindow.setText(
                'Введён не корректный ИНН'
            )  # Если проверка на на длину ИНН не будет пройдена, будет выведено сообщении о некоректности введённых данных
            self.textwindow.adjustSize()  # корриктировка размера
            self.button_save_min_inf.move(1000, 1000)
            self.button_save_full_inf.move(1000, 1000)

    def save_txt(self):
        path = QFileDialog.getExistingDirectory(self, caption='Open file')
        while path == '':
            error_message = QErrorMessage(self)
            error_message.showMessage(f'Необходимо Выбрать путь сохранения файла')
            path = QFileDialog.getExistingDirectory(self, caption='Open file')
        with open(path + '\ИНН_' + self.inn_input.text() + '.txt', 'w', encoding='utf-8') as out_txt:
            out_txt.write(self.textwindow.text())  # создаёт тхт файл, и сохраняет туда краткую информацию

    def del_inf(self):
        self.button_save_full_inf.move(1000, 1000)
        self.button_save_min_inf.move(1000, 1000)
        self.textwindow.setText('данные удалены :)')
        self.inn_input.setText('')
        self.button_delete_inf.move(1000, 1000)

    def start_pdf_report_download_background(self):
        print('Start background report download...')
        if self.active_background_thread:
            mess = QErrorMessage(self)
            mess.showMessage(f'В данный момент уже выполняется загрузка отчёта!')
        path = QFileDialog.getExistingDirectory(self, caption='Open file')
        while path == '':
            error_message = QErrorMessage(self)
            error_message.showMessage(f'Необходимо Выбрать путь сохранения файла')
            path = QFileDialog.getExistingDirectory(self, caption='Open file')
        self.export_worker = PdfExportWorker(self.inn_input.text(), path)
        self.active_background_thread = QThread(self)
        self.export_worker.moveToThread(self.active_background_thread)

        self.active_background_thread.started.connect(self.export_worker.run)
        self.export_worker.complete.connect(self.on_background_pdf_export_complete)
        self.export_worker.finished.connect(self.active_background_thread.quit)
        self.export_worker.finished.connect(self.active_background_thread.deleteLater)
        self.active_background_thread.finished.connect(self.active_background_thread.deleteLater)

        self.active_background_thread.start()
        print('Thread started')

    def on_background_pdf_export_complete(self, filename: str):
        mess = QMessageBox(self)
        mess.setText(f'Файл успешно загружен и сохранён под именем {filename}')
        mess.setWindowTitle('Загрузка отчёта завершена')
        mess.exec()
        self.active_background_thread = None


def application():  # создание главной функции
    app = QApplication(sys.argv)
    window = InnSearchWindow()
    window.show()  # показывает окно GUI, если этой строчки не будет то экземпляр окна GUI просто не будет выведен на экран
    sys.exit(
        app.exec_()
    )  # позволяет закрыть окно GUI без вывода ошибки, т.е. теперь значёк крестика GUI завершает приложеие без ошибок


if __name__ == '__main__':  # запуск основной функции только в случае того, если этот файл будет запущен как основной (т.е. не запущен другим файлом)
    application()

# :) https://music.yandex.ru/users/ser20051227/playlists/1000
