ADVTEST 三机分工 — 拎包入住检查表
================================

0) 若使用 pack_release.ps1 -IncludeNuScenesData 打好的包（默认打 dataset/Trainval：
   maps、samples、test6019_bundle、v1.0-trainval、.v1.0-trainval_meta.txt 等，与仓库侧量产一致）
   分卷传输可加 -SplitArchive（CODE 包 + DATA 包）；细节见包内 README_BUNDLE.txt。
   若需整库 data/nuscenes（极大），加 -DataBundleKind DataNuscenes。
   Trainval 下若有 blobs 等也需打进包：加 -TrainvalFullFolder。
   解压后设：
     ADVTEST_ROOT=<解压根>
     NUSCENES_DATAROOT=<解压根>/dataset/Trainval
     NUSCENES_VERSION=v1.0-trainval
     VQA_QA_JSON=<解压根>/data/nuscenes/qa/NuScenes_val_questions.json（若未随包请另放并改路径）

A) 每台机器各自准备（不要三台共写一个 Excel）
   - 复制 official_pipeline/advtest_runtime.env.example → official_pipeline/advtest_runtime.env
   - 填写 VQA_API_KEY、NEO4J_PASSWORD、ADVTEST_ROOT（本机解压根目录）
   - 必设独立 Excel，避免并发锁：
       ADVTEST_EXCEL_PATH=<ROOT>/data/RQ_server_a.xlsx   （或 _b / _local）
   - 帧任务（三份互不重复）：
       export ADVTEST_FRAME_PLAN_JSON=<ROOT>/nuscenes_s3c_experiment/deploy/frames_server_a.json
     Linux 用 export；Windows PowerShell 用 $env:ADVTEST_FRAME_PLAN_JSON="..."
   - 可选：统一输出目录
       ADVTEST_GEN_QA_DIR=<ROOT>/generated_qa

B) 大数据（建议三台路径一致，或只在一台、其余 NFS）
   - NUSCENES_DATAROOT → 含 v1.0-trainval 的 Trainval 根
   - VQA_QA_JSON → NuScenes_val_questions.json
   若不上传：在 env 里指到服务器已有路径即可。

C) Neo4j
   - 每台可跑独立 Docker 实例（不同端口）或分时共用；同一时刻只跑一条流水线写同一 bolt 即可。

D) 运行量产（V17）
   cd <ROOT>/nuscenes_s3c_experiment/official_pipeline
   python run_v17_production.py

E) 帧分配汇总
   - server_a: 6 帧 → deploy/frames_server_a.json
   - server_b: 6 帧 → deploy/frames_server_b.json
   - local:    2 帧 → deploy/frames_local.json
   全量清单：deploy/frame_plan_all.json（14 帧，上表已分完无遗漏）

F) 合并结果
   - 各机 generated_qa/*.json 与各自 RQ*.xlsx 拉回后，再脚本合并或分别存档。
