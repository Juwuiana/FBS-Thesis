content = open('app/static/css/style.css', encoding='utf-8').read()

# Make view-btn always visible
old = ''
import re

# Add overrides at end
extra = """
/* ── BUTTON VISIBILITY FIXES ── */
.view-btn {
  padding: 5px 14px;
  background: #ffffff;
  color: #27ae60;
  border: 1.5px solid #27ae60;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.view-btn:hover {
  background: #27ae60;
  color: #ffffff;
}
.ps-primary-btn {
  padding: 9px 20px;
  background: #27ae60 !important;
  color: #fff !important;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
}
.ps-secondary-btn {
  padding: 9px 20px;
  background: #ffffff !important;
  color: #27ae60 !important;
  border: 1.5px solid #27ae60 !important;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
}
.ps-primary-btn:hover { background: #219a52 !important; }
.ps-secondary-btn:hover { background: #27ae60 !important; color: #fff !important; }
"""
content += extra
open('app/static/css/style.css', 'w', encoding='utf-8').write(content)
print("Done")
