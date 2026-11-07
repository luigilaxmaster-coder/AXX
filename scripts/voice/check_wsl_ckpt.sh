#!/bin/bash
/opt/axx-piper-train/piper1-gpl/.venv/bin/python3 -c "
import torch
c = torch.load('/opt/axx-piper-train/work/axx-morcito-es/lightning_logs/version_0/checkpoints/last.ckpt', map_location='cpu')
print('Epoch:', c.get('epoch'), 'Global step:', c.get('global_step'))
"
