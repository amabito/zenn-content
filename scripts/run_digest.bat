@echo off
REM Daily Tech Digest - Task Scheduler用バッチファイル
REM 毎朝自動実行: arXiv/GitHub/RSS/Anthropicの新着情報をDiscordに通知

cd /d D:\work\Projects\zenn
python scripts\daily_tech_digest.py --auto-summarize
