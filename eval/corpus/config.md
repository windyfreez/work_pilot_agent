# 配置说明

WorkPilot 通过环境变量配置。文件操作的授权目录由 `WORKPILOT_ALLOWED_DIRS` 指定，
多个目录用分号或逗号分隔。所有文件读写都被限制在授权目录内。
