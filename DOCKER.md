# GPU OCR 环境使用指南（RTX 5060 Blackwell 架构）

## 官方最佳实践

针对 RTX 5060（Blackwell 架构），**使用官方专用 Docker 镜像是最推荐的方式**，能最大程度避免环境兼容性问题。

### 前置要求

1. **NVIDIA 驱动**：必须支持 **CUDA 12.9 或更高版本**
2. **Docker Desktop**：https://www.docker.com/products/docker-desktop/
3. **NVIDIA Container Toolkit**：https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

### 验证驱动

```powershell
nvidia-smi
```

应显示 CUDA Version ≥ 12.9。

## 使用方式

### 方法一：使用官方镜像（推荐）

```powershell
# 设置环境变量
$env:PDF_FILE="要件审判九步法 (邹碧华) (Z-Library).pdf"
$env:OUTPUT_FILE="output.md"

# 运行 OCR 转换（自动拉取官方 Blackwell 专用镜像）
docker compose run --rm lawtomd-gpu
```

镜像说明：
- 镜像名：`paddleocr-vl:latest-nvidia-gpu-sm120`
- 大小：约 10GB
- 后缀 `-sm120` 表示针对 Blackwell 架构优化

### 方法二：使用 vLLM 加速（高吞吐场景）

```powershell
# 启动 vLLM 推理服务
docker run --gpus all -it ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-genai-vllm-server:latest-nvidia-gpu-sm120
```

### 方法三：自定义构建（备选）

```powershell
# 使用本地 Dockerfile 构建
docker compose -f docker-compose.custom.yml build
docker compose -f docker-compose.custom.yml run --rm lawtomd-gpu
```

## 性能调优

根据官方测试，RTX 5060 运行 PP-OCRv4 管线时：
- **FP16 精度**：吞吐量可达 28 页/秒
- **显存占用**：约 1.2GB

优化选项：
- 启用 TensorRT：`--use_tensorrt=True`
- 调整精度：`--precision fp16` 或 `int8`
- 调整显存分配：`--gpu_mem 500`（默认 500MB）

## CPU 模式

```powershell
# 设置环境变量强制使用 CPU
$env:LAWTOMD_USE_GPU="0"
$env:PDF_FILE="test.pdf"
docker compose run --rm lawtomd-gpu
```

## 清理

```powershell
# 停止并删除容器
docker compose down

# 删除镜像（可选）
docker rmi ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-nvidia-gpu-sm120
```

## 注意事项

- 容器只在运行时占用 GPU 资源，运行结束后自动释放
- 输入文件放在 `input/` 目录，输出文件在 `output/` 目录
- 首次运行会下载约 10GB 镜像，可能需要较长时间
- 如遇问题，关注官方文档中关于 "Blackwell" 或 "RTX50" 的最新更新
