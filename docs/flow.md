# Flow

## Folder architecture

```text
News-Big-Data-Platform/
|-- docs/               # Documentations 
|-- data/               # Contains output data of the program
    |-- bronze/             # Raw data crawled from sources 
    |-- silver/             # Cleaning data
    |-- gold/               # Final data ready for business services
|-- src/                # Source code of the program
    |-- config/             # Contains all the configs, schemas, global constants, ... of the program
    |-- crawlers/           # Crawlers
```


## Partial flows

### 1. Config

+ structure:

```text
News-Big-Data-Platform/
|-- src/
    |-- config/
        |-- crawlers.py     # Crawler configs
        |-- ...
```

>[!NOTE]
> Tất cả các config của cả cái dự án này đều phải để trong `src/config/`, ví dụ như biến lấy từ `.env`, global constants (biến dùng chung) giữa các luồng, ...  

>[!WARNING]
> Sau này có thêm luồng nào thì nhớ sửa cái folder structure ở trên  
> KHÔNG hardcode các biến somewhere bên ngoài cái `config/` này  



### 2. Crawler

+ Folder relationship structure

```text
News-Big-Data-Platform/
|-- data/
    |-- bronze/                 # Results saved to this folder
|-- src/
    |-- config/
        |-- crawlers.py             # Crawler configs
    |-- crawlers/
        |-- rss_crawler.py          # Handle crawling RSS Feed
        |-- run.py                  # Run the crawling pipeline
```

+ Input: `RSS_SOURCES` defined at `src/config/crawlers.py`

+ Run pipeline
```bash
cd src
python -m crawlers.run
```

+ Output: `.parquet` files saved in `data/bronze/`


