FROM nvidia/cuda:12.9.0-runtime-ubuntu22.04

# 设置非交互模式
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-venv \
    python3-pip \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY pyproject.toml requirements.txt ./
COPY src/ ./src/

# 安装Python依赖（使用百度源加速）
RUN pip3 install --no-cache-dir \
    paddlepaddle-gpu>=3.2.1 -i https://mirror.baidu.com/pypi/simple && \
    pip3 install --no-cache-dir \
    paddleocr>=3.2.0 \
    onnxruntime-gpu \
    opencv-contrib-python>=4.10.0 \
    PyMuPDF>=1.23.0 \
    Pillow>=10.0 \
    pdfplumber>=0.10 \
    click>=8.0 \
    pyyaml>=6.0

# 设置共享内存大小（避免多进程OCR崩溃）
ENV OMP_NUM_THREADS=4

# 默认命令
ENTRYPOINT ["python3", "-m", "src.main"]
CMD ["--help"]
