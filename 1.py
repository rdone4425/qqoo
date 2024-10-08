import sys
import os
import json
import shutil
import subprocess
import threading
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QListWidget, 
                             QCheckBox, QProgressBar, QFileDialog, QMessageBox,
                             QFrame, QSplitter, QInputDialog, QDialog, QFormLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QIcon
import requests

class WorkerSignals(QObject):
    error = pyqtSignal(str)
    success = pyqtSignal(str)
    progress = pyqtSignal(str)

class NewRepoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建仓库")
        self.setModal(True)
        self.layout = QFormLayout(self)

        self.name_input = QLineEdit(self)
        self.layout.addRow("仓库名称:", self.name_input)

        self.description_input = QLineEdit(self)
        self.layout.addRow("描述 (可选):", self.description_input)

        self.private_checkbox = QCheckBox("私有仓库", self)
        self.layout.addRow(self.private_checkbox)

        self.readme_checkbox = QCheckBox("初始化README文件", self)
        self.layout.addRow(self.readme_checkbox)

        self.buttons = QHBoxLayout()
        self.ok_button = QPushButton("确定", self)
        self.cancel_button = QPushButton("取消", self)
        self.buttons.addWidget(self.ok_button)
        self.buttons.addWidget(self.cancel_button)
        self.layout.addRow(self.buttons)

        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def get_data(self):
        return {
            "name": self.name_input.text(),
            "description": self.description_input.text(),
            "private": self.private_checkbox.isChecked(),
            "auto_init": self.readme_checkbox.isChecked()
        }

class GitHubUploader(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.load_token()
        self.worker_signals = WorkerSignals()
        self.worker_signals.error.connect(self.show_error)
        self.worker_signals.success.connect(self.show_success)
        self.worker_signals.progress.connect(self.update_status)
        self.all_repos = []  # 存储所有仓库

    def initUI(self):
        self.setWindowTitle('GitHub上传工具')
        self.setGeometry(300, 300, 800, 600)
        self.setFont(QFont('Segoe UI', 10))
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                color: #333;
            }
            QLabel {
                font-size: 14px;
            }
            QPushButton {
                background-color: #4a86e8;
                color: white;
                padding: 8px 15px;
                border: none;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3a76d8;
            }
            QLineEdit, QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
                background-color: white;
            }
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
            }
            QListWidget {
                alternate-background-color: #f0f0f0;
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)

        # 仓库列表和搜索
        top_frame = QFrame()
        top_layout = QVBoxLayout(top_frame)

        # 添加搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索仓库...')
        self.search_input.textChanged.connect(self.search_repos)
        top_layout.addWidget(self.search_input)

        self.repo_list = QListWidget()
        self.repo_list.setAlternatingRowColors(True)
        top_layout.addWidget(self.repo_list)

        # 上传按钮
        self.upload_btn = QPushButton('上传到GitHub')
        self.upload_btn.clicked.connect(self.start_upload)
        top_layout.addWidget(self.upload_btn)

        # 新建和删除仓库按钮
        repo_buttons_layout = QHBoxLayout()
        self.new_repo_btn = QPushButton('新建仓库')
        self.new_repo_btn.setIcon(QIcon('path_to_new_repo_icon.png'))
        self.new_repo_btn.clicked.connect(self.create_new_repo)
        repo_buttons_layout.addWidget(self.new_repo_btn)
        self.delete_repo_btn = QPushButton('删除仓库')
        self.delete_repo_btn.setIcon(QIcon('path_to_delete_icon.png'))
        self.delete_repo_btn.clicked.connect(self.delete_repo)
        repo_buttons_layout.addWidget(self.delete_repo_btn)
        top_layout.addLayout(repo_buttons_layout)

        # 文件选择和Token输入
        bottom_frame = QFrame()
        bottom_layout = QVBoxLayout(bottom_frame)

        file_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        file_layout.addWidget(QLabel('选择要上传的文件/文件夹:'))
        file_layout.addWidget(self.path_input)
        self.file_btn = QPushButton('选择文件')
        self.file_btn.setIcon(QIcon('path_to_file_icon.png'))
        self.file_btn.clicked.connect(self.browse_files)
        self.folder_btn = QPushButton('选择文件夹')
        self.folder_btn.setIcon(QIcon('path_to_folder_icon.png'))
        self.folder_btn.clicked.connect(self.browse_folder)
        file_layout.addWidget(self.file_btn)
        file_layout.addWidget(self.folder_btn)
        bottom_layout.addLayout(file_layout)

        token_layout = QHBoxLayout()
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.Password)
        token_layout.addWidget(QLabel('GitHub Token:'))
        token_layout.addWidget(self.token_input)
        self.get_repos_btn = QPushButton('获取仓库列表')
        self.get_repos_btn.clicked.connect(self.get_repos)
        token_layout.addWidget(self.get_repos_btn)
        bottom_layout.addLayout(token_layout)

        self.remember_token = QCheckBox('记住Token')
        bottom_layout.addWidget(self.remember_token)

        # 使用QSplitter来分隔上下两部分
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top_frame)
        splitter.addWidget(bottom_frame)
        main_layout.addWidget(splitter)

        # 进度条和状态显示
        status_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        status_layout.addWidget(self.progress_bar)
        self.status_label = QLabel('准备就绪')
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status_layout.addWidget(self.status_label)
        main_layout.addLayout(status_layout)

        self.setLayout(main_layout)

    def load_token(self):
        try:
            with open('token.json', 'r') as f:
                data = json.load(f)
                self.token_input.setText(data.get('token', ''))
                self.remember_token.setChecked(True)
        except FileNotFoundError:
            pass

    def save_token(self):
        if self.remember_token.isChecked():
            with open('token.json', 'w') as f:
                json.dump({'token': self.token_input.text()}, f)
        else:
            try:
                os.remove('token.json')
            except FileNotFoundError:
                pass

    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        self.path_input.setText(';'.join(files))

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        self.path_input.setText(folder)

    def get_repos(self):
        token = self.token_input.text()
        if not token:
            self.show_error("请输入GitHub Token")
            return

        try:
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }
            self.all_repos = []
            page = 1
            while True:
                response = requests.get(f"https://api.github.com/user/repos?page={page}&per_page=100", headers=headers)
                if response.status_code == 200:
                    repos = response.json()
                    if not repos:
                        break
                    self.all_repos.extend(repos)
                    page += 1
                else:
                    raise Exception(f"获取仓库列表失败: {response.json()['message']}")

            self.update_repo_list()
            self.show_success(f"已获取 {len(self.all_repos)} 个仓库")
        except Exception as e:
            self.show_error(f"获取仓库列表失败: {str(e)}")

    def update_repo_list(self, filter_text=''):
        self.repo_list.clear()
        for repo in self.all_repos:
            repo_name = repo['full_name']
            if repo['private']:
                repo_name += " (私有)"
            if filter_text.lower() in repo_name.lower():
                self.repo_list.addItem(repo_name)

    def search_repos(self):
        search_text = self.search_input.text()
        self.update_repo_list(search_text)

    def create_new_repo(self):
        dialog = NewRepoDialog(self)
        if dialog.exec_():
            repo_data = dialog.get_data()
            token = self.token_input.text()
            if not token:
                self.show_error("请先输入GitHub Token")
                return
            try:
                repo_url = self.create_repo(token, repo_data)
                self.repo_list.addItem(repo_data['name'])
                self.show_success(f"成功创建仓库: {repo_data['name']}")
                self.get_repos()  # 刷新仓库列表
            except Exception as e:
                self.show_error(f"创建仓库失败: {str(e)}")

    def start_upload(self):
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("正在上传...")
        threading.Thread(target=self.upload_to_github, daemon=True).start()

    def create_repo(self, token, repo_data):
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        response = requests.post("https://api.github.com/user/repos", headers=headers, json=repo_data)
        if response.status_code == 201:
            return response.json()["clone_url"]
        else:
            raise Exception(f"创建仓库失败: {response.json()['message']}")

    def upload_to_github(self):
        paths = self.path_input.text().split(';')
        token = self.token_input.text()
        selected_repo = self.repo_list.currentItem().text() if self.repo_list.currentItem() else None

        if not paths or not token:
            self.worker_signals.error.emit("请选择文件/文件夹并填写GitHub Token")
            return

        try:
            if not selected_repo:
                self.worker_signals.error.emit("请选择一个仓库")
                return

            selected_repo = selected_repo.split(" (私有)")[0]
            repo_url = f"https://github.com/{selected_repo}.git"

            temp_dir = os.path.join(os.path.expanduser("~"), "temp_git_upload")
            os.makedirs(temp_dir, exist_ok=True)
            os.chdir(temp_dir)

            self.run_git_command(["git", "init"])
            
            # 添加远程仓库
            token_url = repo_url.replace("https://", f"https://{token}@")
            self.run_git_command(["git", "remote", "add", "origin", token_url])
            
            # 获取远程仓库的默认分支
            default_branch = self.get_default_branch(token, selected_repo)
            
            # 尝试拉取远程仓库内容
            try:
                self.run_git_command(["git", "fetch", "origin", default_branch])
                self.run_git_command(["git", "checkout", "-b", default_branch, f"origin/{default_branch}"])
            except subprocess.CalledProcessError:
                # 如果拉取失败，可能是因为远程仓库是空的，我们创建一个新的分支
                self.run_git_command(["git", "checkout", "-b", default_branch])

            # 复制新文件到临时目录
            for path in paths:
                if os.path.isfile(path):
                    shutil.copy2(path, temp_dir)
                elif os.path.isdir(path):
                    shutil.copytree(path, os.path.join(temp_dir, os.path.basename(path)), dirs_exist_ok=True)

            # 添加并提交新文件
            self.run_git_command(["git", "add", "."])
            self.run_git_command(["git", "commit", "-m", "Add new files"])

            # 推送到GitHub
            try:
                self.run_git_command(["git", "push", "-u", "origin", default_branch])
            except subprocess.CalledProcessError:
                # 如果推送失败，尝试先拉取然后再推送
                self.run_git_command(["git", "pull", "--rebase", "origin", default_branch])
                self.run_git_command(["git", "push", "-u", "origin", default_branch])

            self.worker_signals.success.emit("文件已成功上传到GitHub")
            self.save_token()
        except Exception as e:
            self.worker_signals.error.emit(f"上传失败: {str(e)}")
        finally:
            self.progress_bar.setRange(0, 1)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def get_default_branch(self, token, repo):
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        response = requests.get(f"https://api.github.com/repos/{repo}", headers=headers)
        if response.status_code == 200:
            return response.json()["default_branch"]
        else:
            return "main"  # 如果无法获取，默认使用 'main'

    def run_git_command(self, command):
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            self.worker_signals.progress.emit(result.stdout.strip() or result.stderr.strip())
        except subprocess.CalledProcessError as e:
            raise Exception(f"命令 '{' '.join(command)}' 失败: {e.stderr}")

    def show_error(self, message):
        self.progress_bar.setRange(0, 1)
        self.status_label.setText("错误")
        QMessageBox.critical(self, "错误", message)

    def show_success(self, message):
        self.progress_bar.setRange(0, 1)
        self.status_label.setText("成功")
        QMessageBox.information(self, "成功", message)

    def update_status(self, message):
        self.status_label.setText(message)

    def delete_repo(self):
        selected_repo = self.repo_list.currentItem()
        if not selected_repo:
            self.show_error("请选择要删除的仓库")
            return

        repo_name = selected_repo.text().split(" (私有)")[0]
        confirm = QMessageBox.question(self, '确认删除', f"确定要删除仓库 {repo_name} 吗？\n此操作不可逆！",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm == QMessageBox.Yes:
            token = self.token_input.text()
            if not token:
                self.show_error("请先输入GitHub Token")
                return
            try:
                self.delete_github_repo(token, repo_name)
                self.show_success(f"成功删除仓库: {repo_name}")
                self.get_repos()  # 刷新仓库列表
            except Exception as e:
                self.show_error(f"删除仓库失败: {str(e)}")

    def delete_github_repo(self, token, repo_name):
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        response = requests.delete(f"https://api.github.com/repos/{repo_name}", headers=headers)
        if response.status_code != 204:
            raise Exception(f"删除仓库失败: {response.json().get('message', '未知错误')}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 使用Fusion风格以获得更现代的外观
    ex = GitHubUploader()
    ex.show()
    sys.exit(app.exec_())