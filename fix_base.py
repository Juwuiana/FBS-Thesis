import re

html = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}FBS Diabetes Risk{% endblock %}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --sidebar-w: 185px;
            --g-darkest: #0f2318;
            --g-dark:    #163020;
            --g-mid:     #1e4028;
            --g-accent:  #27ae60;
            --bg:        #f0f4f1;
            --white:     #ffffff;
            --t1:        #1e293b;
            --t2:        #475569;
            --t3:        #94a3b8;
            --border:    #e2e8f0;
        }
        html, body { font-family: 'DM Sans', sans-serif; font-size: 14px; height: 100%; }
        body { display: flex; min-height: 100vh; background: var(--bg); color: var(--t1); }
        .sidebar { width: var(--sidebar-w); background: var(--g-dark); color: #fff; display: flex; flex-direction: column; position: fixed; top: 0; left: 0; bottom: 0; z-index: 200; overflow-y: auto; }
        .sidebar-top { display: flex; align-items: center; gap: 0.75rem; padding: 1.1rem 1rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.07); }
        .sidebar-logo { width: 36px; height: 36px; background: #c0392b; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 0.6rem; font-weight: 800; color: #fff; text-align: center; line-height: 1.1; padding: 4px; }
        .sidebar-brand-text { font-size: 0.72rem; font-weight: 700; line-height: 1.35; color: #fff; }
        .sidebar-nav { flex: 1; padding: 1rem 0; }
        .nav-item { display: block; padding: 0.7rem 1.25rem; color: rgba(255,255,255,0.6); text-decoration: none; font-size: 0.82rem; font-weight: 400; transition: background 0.15s, color 0.15s; border-left: 3px solid transparent; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .nav-item:hover { color: #fff; background: rgba(255,255,255,0.06); }
        .nav-item.active { background: rgba(255,255,255,0.08); color: #fff; border-left-color: var(--g-accent); font-weight: 600; }
        .sidebar-user { padding: 0.9rem 1rem; background: rgba(0,0,0,0.2); display: flex; align-items: center; gap: 0.6rem; cursor: pointer; position: relative; }
        .sidebar-user:hover { background: rgba(0,0,0,0.3); }
        .user-avatar-circle { width: 34px; height: 34px; border-radius: 50%; background: var(--g-accent); display: flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 700; color: #fff; flex-shrink: 0; overflow: hidden; }
        .user-avatar-circle img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }
        .user-info { flex: 1; min-width: 0; }
        .user-name { font-size: 0.78rem; font-weight: 600; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .user-role { font-size: 0.68rem; color: rgba(255,255,255,0.5); }
        .user-dropdown { display: none; position: absolute; bottom: calc(100% + 4px); left: 0.5rem; right: 0.5rem; background: #fff; border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.15); overflow: hidden; z-index: 300; }
        .user-dropdown.open { display: block; }
        .user-dropdown-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.7rem 1rem; font-size: 0.82rem; color: var(--t1); text-decoration: none; cursor: pointer; transition: background 0.15s; }
        .user-dropdown-item:hover { background: #f0f4f0; }
        .user-dropdown-signout { color: #dc2626; }
        .main-wrapper { flex: 1; margin-left: var(--sidebar-w); background: var(--bg); min-height: 100vh; display: flex; flex-direction: column; }
        .admin-topbar { display: flex; align-items: center; justify-content: space-between; padding: 0.85rem 2rem; background: var(--g-darkest); color: rgba(255,255,255,0.85); font-size: 0.82rem; gap: 1rem; position: sticky; top: 0; z-index: 100; }
        .topbar-left { display: flex; align-items: center; gap: 0.75rem; }
        .hamburger-btn { background: none; border: none; color: rgba(255,255,255,0.7); font-size: 1.1rem; cursor: pointer; padding: 2px 4px; display: none; }
        .topbar-title { font-size: 1.05rem; font-weight: 600; color: #fff; }
        .topbar-right { display: flex; align-items: center; gap: 0.75rem; }
        .topbar-date { font-size: 0.75rem; color: rgba(255,255,255,0.5); }
        .bell-btn { background: none; border: none; color: rgba(255,255,255,0.7); font-size: 1.1rem; cursor: pointer; padding: 4px; }
        .page-content { padding: 1.75rem 2rem; flex: 1; }
        .sidebar-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 190; }
        .sidebar-overlay.open { display: block; }
        .back-to-top { position: fixed; bottom: 1.5rem; right: 1.5rem; width: 36px; height: 36px; background: var(--g-accent); color: #fff; border: none; border-radius: 50%; font-size: 1rem; cursor: pointer; display: none; align-items: center; justify-content: center; z-index: 500; }
        .back-to-top.show { display: flex; }
        @media (max-width: 900px) {
            .sidebar { transform: translateX(-100%); transition: transform 0.25s ease; }
            .sidebar.open { transform: translateX(0); }
            .main-wrapper { margin-left: 0; }
            .hamburger-btn { display: block; }
            .page-content { padding: 1.25rem; }
            .admin-topbar { padding: 0.75rem 1rem; }
        }
    </style>
    {% block head %}{% endblock %}
</head>
<body>
<div class="sidebar-overlay" id="sidebarOverlay"></div>
<aside class="sidebar" id="sidebar">
    <div class="sidebar-top">
        <div class="sidebar-logo">FBS<br>LHU</div>
        <div class="sidebar-brand-text">FBS-Based<br>Diabetes Risk<br>Prediction</div>
    </div>
    <nav class="sidebar-nav">
        <a href="{{ url_for('admin.dashboard') }}" class="nav-item {{ 'active' if active_page == 'dashboard' else '' }}">Dashboard</a>
        <a href="{{ url_for('admin.reliability') }}" class="nav-item {{ 'active' if active_page == 'reliability' else '' }}">Model Reliability</a>
        <a href="{{ url_for('admin.green_computing') }}" class="nav-item {{ 'active' if active_page == 'green_computing' else '' }}">Green Computing</a>
        <a href="{{ url_for('admin.data_management') }}" class="nav-item {{ 'active' if active_page == 'data_management' else '' }}">Data Management</a>
        <a href="{{ url_for('admin.audit_trails') }}" class="nav-item {{ 'active' if active_page == 'audit_trails' else '' }}">Audit Trails</a>
        <a href="{{ url_for('admin.privacy_security') }}" class="nav-item {{ 'active' if active_page == 'privacy' else '' }}">Privacy &amp; Security</a>
    </nav>
    <div class="sidebar-user" id="userMenuToggle">
        <div class="user-avatar-circle" id="userAvatarCircle">
            <img id="userAvatarImg" src="" alt="" style="display:none;">
            <span id="userAvatarInitials">HO</span>
        </div>
        <div class="user-info">
            <div class="user-name">Health Officer</div>
            <div class="user-role">LHU Cabuyao</div>
        </div>
    </div>
    <div class="user-dropdown" id="userDropdown">
        <label class="user-dropdown-item" for="avatarFileInput">
            🖼 Change Photo
            <input type="file" id="avatarFileInput" accept="image/*" style="display:none;">
        </label>
        <a href="{{ url_for('auth.logout') }}" class="user-dropdown-item user-dropdown-signout">🚪 Sign Out</a>
    </div>
</aside>
<div class="main-wrapper">
    <div class="admin-topbar">
        <div class="topbar-left">
            <button class="hamburger-btn" id="hamburgerBtn">&#9776;</button>
            <span class="topbar-title">{% block page_title %}{% endblock %}</span>
        </div>
        <div class="topbar-right">
            <span class="topbar-date" id="topbarDate"></span>
            <button class="bell-btn">&#128276;</button>
        </div>
    </div>
    <div class="page-content">
        {% block content %}{% endblock %}
    </div>
</div>
<button class="back-to-top" id="backToTop">&#8593;</button>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="{{ url_for('static', filename='js/main.js') }}"></script>
<script>
document.addEventListener('DOMContentLoaded', () => {
    const sidebar=document.getElementById('sidebar'),overlay=document.getElementById('sidebarOverlay'),hamburger=document.getElementById('hamburgerBtn'),backToTop=document.getElementById('backToTop');
    if(hamburger)hamburger.addEventListener('click',()=>{sidebar.classList.toggle('open');overlay.classList.toggle('open');});
    if(overlay)overlay.addEventListener('click',()=>{sidebar.classList.remove('open');overlay.classList.remove('open');});
    window.addEventListener('scroll',()=>{backToTop.classList.toggle('show',window.scrollY>300);});
    if(backToTop)backToTop.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));
    const dateEl=document.getElementById('topbarDate');
    if(dateEl){const now=new Date();dateEl.textContent=now.toLocaleDateString('en-PH',{year:'numeric',month:'long',day:'numeric'});}
    const toggle=document.getElementById('userMenuToggle'),dropdown=document.getElementById('userDropdown');
    if(toggle)toggle.addEventListener('click',(e)=>{e.stopPropagation();dropdown.classList.toggle('open');});
    document.addEventListener('click',()=>dropdown&&dropdown.classList.remove('open'));
    const avatarInput=document.getElementById('avatarFileInput'),avatarImg=document.getElementById('userAvatarImg'),avatarInitials=document.getElementById('userAvatarInitials'),AVATAR_KEY='adminAvatarDataUrl';
    const saved=localStorage.getItem(AVATAR_KEY);
    if(saved&&avatarImg){avatarImg.src=saved;avatarImg.style.display='block';if(avatarInitials)avatarInitials.style.display='none';}
    if(avatarInput){avatarInput.addEventListener('change',()=>{const file=avatarInput.files[0];if(!file)return;const reader=new FileReader();reader.onload=e=>{localStorage.setItem(AVATAR_KEY,e.target.result);avatarImg.src=e.target.result;avatarImg.style.display='block';if(avatarInitials)avatarInitials.style.display='none';dropdown.classList.remove('open');};reader.readAsDataURL(file);});}
});
</script>
{% block scripts %}{% endblock %}
</body>
</html>"""

open('app/templates/base.html', 'w', encoding='utf-8').write(html)
print('base.html written successfully')
