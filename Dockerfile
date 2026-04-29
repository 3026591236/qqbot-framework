FROM python:3.11-slim

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} --trusted-host ${PIP_TRUSTED_HOST} -r requirements.txt || \
    pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x /app/run.sh
EXPOSE 9000
CMD ["/bin/sh", "/app/run.sh"]
