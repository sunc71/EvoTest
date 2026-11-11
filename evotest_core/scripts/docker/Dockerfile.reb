FROM curiositybench:latest

# 安装覆盖率和测试依赖（与 testgeneval 的 sweb.eval 镜像对齐）
RUN pip install --no-cache-dir coverage pytest

# 验证安装
RUN python3 -c "import coverage; import pytest; print('Dependencies OK')"
