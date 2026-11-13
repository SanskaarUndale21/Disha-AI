Set-Location D:\coding\Hackvalley
Wait-Process -Id 33076 -ErrorAction SilentlyContinue
& .venv\Scripts\python.exe ml/train.py --base models/pothole_r2.pt --data data/pothole_fast/data.yaml --epochs 3 --batch 8 --workers 2 --name pothole_wx --out models/pothole_wx.pt --patience 3 --lr0 0.0003 *> train_pothole_wx.log
