cd /d D:\tracex\TraceX-FinTech
"git" add -A
"git" commit -m "Integrate frontend + reliability fixes: monitoring, tests, contracts, API patches" || echo No new commit
"git" fetch origin
"git" branch -f backup-origin-main origin/main
"git" push origin backup-origin-main:refs/heads/backup/origin-main
"git" push --force origin main
echo Done
