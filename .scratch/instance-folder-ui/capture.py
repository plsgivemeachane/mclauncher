"""Render the real Qt interface with isolated sample instances and no network."""
from pathlib import Path
from tempfile import TemporaryDirectory
from PySide6.QtWidgets import QApplication, QScrollArea
from mclauncher.app import LauncherWindow

app = QApplication([])
LauncherWindow._start_version_discovery = lambda self: None
output = Path(__file__).parent
with TemporaryDirectory(prefix='mclauncher-ui-', dir='/tmp') as directory:
    window = LauncherWindow(data_root=Path(directory))
    window.username_input.setText('Alex')
    window.username_input.editingFinished.emit()
    for index, name in enumerate(('Survival', 'Creative', 'Fabric Adventures')):
        instance = {'id': f'setup-{index:08x}', 'name': name, 'version': '1.21.4', 'ready': True}
        window.state['instances'].append(instance)
        window._add_instance_item(instance)
    window.instance_list.setCurrentRow(0)
    window.show()
    for width, height in ((920, 560), (680, 420), (1885, 1010)):
        window.resize(width, height)
        for page, label in ((0, 'home'), (1, 'instances')):
            window._show_page(page)
            for _ in range(3):
                app.processEvents()
            window.grab().save(str(output / f'{label}-{width}.png'))
            print(label, width, 'actual', window.width(), window.height(), 'folder', window.open_folder_button.geometry())
    window.resize(680, 420)
    window._show_page(1)
    for _ in range(3):
        app.processEvents()
    window.findChild(QScrollArea, 'instanceToolsScroll').ensureWidgetVisible(window.install_optifine_button)
    window.findChild(QScrollArea, 'instanceLibraryScroll').ensureWidgetVisible(window.create_instance_button)
    app.processEvents()
    window.grab().save(str(output / 'instances-680-scrolled.png'))
    window.close()
