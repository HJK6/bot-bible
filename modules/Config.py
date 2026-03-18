import os

# Table names (resolved from CloudFormation !Ref at deploy time)
AGENT_TRACKER_TABLE = os.environ.get("AGENT_TRACKER_TABLE", "AgentTracker")
AGENT_LOGS_TABLE = os.environ.get("AGENT_LOGS_TABLE", "AgentLogs")
AGENT_COMMANDS_TABLE = os.environ.get("AGENT_COMMANDS_TABLE", "AgentCommands")
AGENT_CHAT_TABLE = os.environ.get("AGENT_CHAT_TABLE", "AgentChat")
PUSH_TOKENS_TABLE = os.environ.get("PUSH_TOKENS_TABLE", "PushTokens")
BOT_TRACKER_TABLE = os.environ.get("BOT_TRACKER_TABLE", "BotTracker")
BSE_STOCKS_TABLE = os.environ.get("BSE_STOCKS_TABLE", "BSEStocks")
VOLUME_SHOCKS_TABLE = os.environ.get("VOLUME_SHOCKS_TABLE", "VolumeShocks")
TRADES_TABLE = os.environ.get("TRADES_TABLE", "Trades")
PROJECTS_TABLE = os.environ.get("PROJECTS_TABLE", "Projects")

# S3 (resolved from SSM at deploy time)
CODE_BUCKET = os.environ.get("CODE_BUCKET", "altum-deployment-assets")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "YOUR_BOT_NAME-chat-media")

# Region
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
