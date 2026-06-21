"""python -m web.api 启动 uvicorn"""
import uvicorn

from config import API_HOST, API_PORT


def main():
    uvicorn.run("web.api.app:app", host=API_HOST, port=API_PORT, reload=False)


if __name__ == "__main__":
    main()
