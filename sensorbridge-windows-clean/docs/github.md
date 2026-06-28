# GitHub Sync

This directory can be initialized and pushed with:

```powershell
git init
git add .
git commit -m "Initial SensorBridge Windows prototype"
gh repo create sensorbridge-windows --private --source . --remote origin --push
```

If `gh auth status` is not logged in, run:

```powershell
gh auth login
```
