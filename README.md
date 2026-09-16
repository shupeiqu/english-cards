# 英语卡片 English Cards

一个用于收藏英文、查看中文释义和练习记忆的 macOS 桌面程序。当前版本：2.8。

## 功能

- 手动添加英文和中文，中文留空时自动翻译。
- 在支持 macOS 系统服务的应用中，选中英文后收藏。
- 自定义每轮条数，随机学习或按收藏时间从早到晚学习，也可手动选择词条。
- 点击卡片显示中文并朗读英文，再点可以重听。
- “熟悉”移出本轮，“不熟悉”放到队尾稍后复习。
- 本地保存收藏和学习进度。

## 运行

适用于 macOS。请先安装 [Python.org 的 Python 3.12](https://www.python.org/downloads/macos/)，包含 Tkinter。程序只使用 Python 标准库，无需安装第三方 Python 包。

在项目文件夹中运行：

```sh
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 app.py
```

也可双击“启动英语卡片.command”。通过网页下载的脚本若无法双击，在项目文件夹中执行 `zsh 启动英语卡片.command`。

此仓库提供源码；源码启动脚本会打开终端。已有的“英语卡片.app”版本可直接双击打开界面。

## 划词收藏

运行一次以下命令，安装当前用户的系统服务：

```sh
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 install.py
```

然后在支持系统服务的应用中选中英文，使用“服务 → 收藏到英语卡片”。如果右键菜单没有服务，可查看顶部应用菜单中的“服务”。安装会将程序复制到当前用户的 `~/Library/Application Support/EnglishCards/program/`，并创建 `~/Library/Services/收藏到英语卡片.workflow`。

## 翻译、语音与数据

自动翻译通过 MyMemory 服务发送所收藏的英文，需要联网，并受服务额度限制。翻译失败时保留英文，可重试或手动补充中文。

英语发音使用 macOS 自带的 `say` 和 Samantha 语音。卡片切换后会停止当前发音。

收藏数据库位于 `~/Library/Application Support/EnglishCards/cards.sqlite3`，与源码文件夹分开存放。不要删除整个 EnglishCards 数据文件夹。

仓库不包含个人收藏、日志或旧代码备份。个人收藏数据库保存在本机，不随源码上传。

## 测试

在项目根目录执行：

```sh
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m unittest discover -s tests -v
```

测试使用临时数据库，覆盖学习队列、学习条数、顺序、释义显示、发音调用、收藏与翻译。语音调用在自动测试中使用模拟对象；实际窗口和扬声器效果需要在 Mac 上确认。

## 许可证

本项目采用 MIT License 开源，详情请参阅仓库中的 `LICENSE` 文件。
