# TryHackMe Streak Bot

An automated bot that maintains your TryHackMe streak using GitHub Actions. Set it up once and never worry about losing your streak again!

## 🔥 Features

- **Fully Automated**: Runs in GitHub Actions cloud - no local computer needed
- **Secure**: Your credentials are stored as encrypted GitHub secrets
- **Reliable**: Powered by GitHub's robust infrastructure
- **CAPTCHA Solver**: Automatically bypasses TryHackMe's reCAPTCHA
- **Detailed Logs**: Every action is logged and stored as GitHub artifacts
- **Customizable Schedule**: Set your preferred time for the daily check-in

## ⚠️ Important Requirements

Before using this bot, you **MUST** join the [polkit room on TryHackMe](https://tryhackme.com/room/polkit). The bot specifically interacts with this room to maintain your streak.

The bot works by:
1. Logging into your TryHackMe account
2. Navigating to the polkit room
3. Resetting progress and completing an action to maintain your streak
4. Verifying the streak counter has increased

If you haven't joined this room, the bot will not function correctly.

## 🛠️ Setup

### 1. Fork this repository

Start by forking this repository to your GitHub account.

### 2. Configure your TryHackMe credentials

Navigate to your forked repository's Settings → Secrets and Variables → Actions, and add the following repository secrets:

- `THM_EMAIL`: Your TryHackMe email address
- `THM_PASSWORD`: Your TryHackMe password

### 3. Adjust the schedule (optional)

By default, the bot runs daily at 12:30 UTC. You can modify this in the `.github/workflows/thmbot.yml` file:

```yaml
schedule:
  - cron: '30 12 * * *'  # Format: minute hour day-of-month month day-of-week
```

### 4. Enable GitHub Actions

Go to the Actions tab in your repository and enable workflows if prompted.

## 📊 Monitoring

### Checking logs

After each run:
1. Go to the Actions tab in your repository
2. Click on the latest workflow run
3. Download the "thm-bot-logs" artifact to view detailed logs

### Manual trigger

You can manually trigger the workflow at any time:
1. Go to the Actions tab
2. Select "TryHackMe Streak Bot" workflow
3. Click "Run workflow"

## 📖 How It Works

The bot uses Selenium with Firefox in headless mode to:
1. Log in to your TryHackMe account
2. Solve any CAPTCHA challenges using audio recognition
3. Navigate to the polkit room
4. Reset progress and complete an action to maintain your streak
5. Verify the streak counter has increased
6. Log all actions for review

## 📝 Troubleshooting

- **Failed Runs**: Check the workflow logs for specific error messages
- **CAPTCHA Issues**: If Google's reCAPTCHA patterns have changed, an update might be needed
- **IP Blocking**: If you notice unusual failures, TryHackMe might be rate-limiting the GitHub Actions IP ranges
- **Room Access**: Ensure you have joined the polkit room on your TryHackMe account

## ⚠️ Disclaimer

This tool is provided for educational purposes only. Please use responsibly and in accordance with TryHackMe's terms of service. The authors are not responsible for any misuse or consequences thereof.

## 🤝 Contributing

Contributions are welcome! Feel free to submit a pull request or open an issue if you have any suggestions or improvements.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---
Auto-configured by Zero Restrictions Agent
