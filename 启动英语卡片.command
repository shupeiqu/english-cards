#!/bin/zsh
cd "${0:A:h}"
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 app.py
if [ $? -ne 0 ]; then
  read '?启动失败，请检查上面的错误信息。按回车关闭…'
fi
