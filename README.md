# XAMPP Guard

```
__  ______ _   _   _    ____  ____  
\ \/ / ___| | | | / \  |  _ \|  _ \ 
 \  / |  _| | | |/ _ \ | |_) | | | |
 /  \ |_| | |_| / ___ \|  _ <| |_| |
/_/\_\____|\___/_/   \_\_| \_\____/ XAMPPGUARD
```

## **Your Data's Last Line Of Defense**
When Your Database Fails To Start, Recovery Can Be Nearly Impossible. **XAMPP Guard** Ensures You’re Always Ready With Reliable Backups — Even In Disaster Scenarios. Designed For Developers Who Value Data Integrity And Need Instant Recovery Options.

---

## 📑 Table Of Contents
- [Features](#-features)
- [Backup Output Structure](#-backup-output-structure)
- [Installation](#%EF%B8%8F-installation)
- [Usage](#%EF%B8%8F-usage)
- [Disclaimer](#%EF%B8%8F-disclaimer)
- [License](#-license)

---

## 🚀 Features

- **Core Backup** – Create A Complete ZIP Archive Of Your Entire XAMPP Folder, Excluding Backups.
- **Database Backup (MariaDB)** – Safely Dump Each Database Into Individual SQL Files And Package Them Into A Single ZIP.
- **Web Root Backup** – Archive Your Entire `htdocs` Folder With Progress Tracking.
- **Progress Bar & Detailed Summary** – Real-Time Progress Visualization And Success/Error Reporting.
- **Cold Copy Mode** – Backup Databases Even When MySQL Server Fails To Start.

---

## 📂 Backup Output Structure

- **Core**  
  `<Drive>:/xampp/guard/backup/core/YYYY/MM/DD/<CID>.zip`
- **Database**  
  `<Drive>:/xampp/guard/backup/database/YYYY/MM/DD/<DID>.zip`
- **Web Root**  
  `<Drive>:/xampp/guard/backup/htdocs/YYYY/MM/DD/<WRID>.zip`

---

## ⚙️ Installation

1. Ensure **Python 3.11+** Is Installed.
2. Install Requirements (Optional But Recommended For Colors):
   ```bash
   pip install -r requirements.txt
   ```
3. Run The `xampp_guard.py` File As Administrator, Preferably Using Windows PowerShell.

---

## 🖥️ Usage

Run From Terminal Or PowerShell:
```bash
python xampp_guard.py
```

### Main Menu
```
1) Core Backup :: XAMPP Folder (Zip Only)
2) Database :: Backup (XAMPP/MariaDB) (Zip Only)
3) Web Root :: Backup (htdocs) (Zip Only)
4) Exit
```

---

## ⚠️ Disclaimer
This Tool Is Provided "As-Is" Without Warranty. Use At Your Own Risk. Always Test Restores Before Relying On Backups In Production Environments.

---

## 📜 License
MIT License – Feel Free To Modify And Share.
