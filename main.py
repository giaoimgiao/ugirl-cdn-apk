# -*- coding: utf-8 -*-
"""
UGIRL CDN Android 启动器
启动本地 HTTP 服务 + 打开系统浏览器
"""
import threading, time, os, sys

import ugirl_cdn_app as app

if 'ANDROID_ARGUMENT' in os.environ:
    app.DATA_DIR = os.path.dirname(os.environ.get('ANDROID_ARGUMENT', '/data/data/org.ugirl.ugirlcdn/files/app'))
    app.ACC_FILE = os.path.join(app.DATA_DIR, 'ugirl_app_accounts.json')

def serve():
    try:
        app.HTTPServer(('0.0.0.0', app.PORT), app.Handler).serve_forever()
    except Exception as e:
        print('serve error:', e)

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button

class CdnApp(App):
    def build(self):
        root = BoxLayout(orientation='vertical', padding=30, spacing=20)
        root.add_widget(Label(
            text='[b]UGIRL 免费CDN[/b]\n本地版已启动\n\n端口: 8866\n服务: http://127.0.0.1:8866',
            markup=True, font_size='20sp', halign='center'))
        btn = Button(text='打开浏览器', size_hint=(1, None), height='60dp',
                     background_color=(0, 0.9, 0.46, 1), font_size='18sp')
        btn.bind(on_press=self.open_browser)
        root.add_widget(btn)
        return root

    def open_browser(self, *args):
        try:
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            it = Intent(Intent.ACTION_VIEW, Uri.parse('http://127.0.0.1:8866'))
            PythonActivity.mActivity.startActivity(it)
        except Exception as e:
            print('open browser err:', e)

if __name__ == '__main__':
    threading.Thread(target=serve, daemon=True).start()
    CdnApp().run()