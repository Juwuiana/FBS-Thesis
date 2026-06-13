content = open('app/templates/base.html', encoding='utf-8').read()

old = '        :root {\n            --sidebar-w: 185px;\n            --g-darkest: #0f2318;\n            --g-dark:    #163020;'

new = '        :root {\n            --sidebar-w: 185px;\n            --g-darkest: #0f2318;\n            --g-dark:    #133c20;'

result = content.replace(old, new)
if result == content:
    print("ERROR: color string not found")
else:
    open('app/templates/base.html', 'w', encoding='utf-8').write(result)
    print("Sidebar color fixed")
