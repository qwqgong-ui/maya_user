# maya_user

`qwqgong-ui` 的 Maya 用户工具库。

当前类目：**多边形建模**。

## 圆角切角

Maya 菜单入口：`Maya User > 多边形建模 > 圆角切角…`

中文参数面板包含：

- 模式：百分比 / 固定距离
- 边界百分比
- 固定距离
- 圆弧段数
- 外角方向（默认翻转）

选择规则：

- 选择 1 个边界顶点：处理外角
- 选择 2 条共享顶点的边界边：处理内角

百分比模式为了保持严格相切圆弧，会以两侧边界允许切入距离中的较小值作为统一切入距离。

## 安装

推荐将仓库克隆到任意位置，然后把仓库根目录加入 `MAYA_MODULE_PATH`。仓库根目录包含 `maya_user.mod`，Maya 启动后会通过 `scripts/userSetup.py` 自动创建 `Maya User` 菜单。

Windows 示例：

```text
MAYA_MODULE_PATH=C:/Users/<用户名>/Documents/maya/modules/maya_user
```

或者把 `maya_user.mod` 放到 Maya 已有的 modules 搜索目录，并将模块路径按实际安装位置调整。

重启 Maya 后即可从 `Maya User > 多边形建模` 打开工具。
