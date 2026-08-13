# 说明：Windows 请在 Git Bash / WSL 中运行本 Makefile（cmd 不原生支持 make）
# 虚拟环境使用 venv/，命令前缀为 venv/Scripts/python.exe

.PHONY: install web cli test clean

install:
	python -m venv venv
	venv/Scripts/python.exe -m pip install -r requirements.txt

web:
	venv/Scripts/python.exe stage5_web.py

cli:
	venv/Scripts/python.exe stage4_agent.py

test:
	venv/Scripts/python.exe -m pytest -q

clean:
	rm -rf __pycache__ .pytest_cache .gradio chroma chroma.sqlite3
