FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 kiwikind && mkdir /data && chown kiwikind /data
COPY --chown=kiwikind:kiwikind . .
USER kiwikind
EXPOSE 8000
CMD ["sh", "deploy/start.sh"]
