# IST Automation Bot
Automation & moderation utilities for the Imperial Shock Troopers Discord server and its academy.

## ✨ Features

- Weekly staff polls
- Detailed event logs
- Invite tracking & management
- Developer cog management system
- Dynamic config & hot-reload support

## 📦 Installation

### 1. Clone the repository
git clone https://github.com/YOURNAME/ist-automation-bot.git
cd ist-automation-bot

### 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

### 3. Install dependencies
pip install -r requirements.txt

### 4. Setup environment variables
copy .env.example .env

### 5. Configure the bot
copy config/config.yaml.example config/config.yaml

### 6. Run the bot
python bot.py

---

## ⚙️ Configuration

All bot settings are stored in:

config/config.yaml

You can reload the config without restarting the bot.

---

## 🧩 Cogs

Cogs can be enabled in:

config/config.yaml

They can be loaded/unloaded live via developer commands.

---

## 🔐 Permissions

The bot requires:

- Send Messages
- Embed Links
- Add Reactions
- Read Message History
- Create Invite
- View Audit Log (optional for event logs)

---

## 🛠 Developer Commands

| Command | Description |
|--------|--------|
| `/developer cog load` | Load a cog |
| `/developer cog unload` | Unload a cog |
| `/developer cog reload` | Reload a cog |
| `/developer config reload` | Reload config |

---

## 📁 Project Structure

See below for folder layout.

---

## 🤝 Contributing

Pull requests welcome. Please open an issue first to discuss major changes.

---

## 📜 License

MIT License (or your choice)
