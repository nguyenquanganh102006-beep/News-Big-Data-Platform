from .rss_vnexpress import rss_vnexpress_preprocessor
from .rss_vietnamplus import rss_vietnamplus_preprocessor
from .rss_tuoitre import rss_tuoitre_preprocessor


def run_preprocessors(crawled_date: str | None = None):
    rss_vnexpress_preprocessor(save_file=True, crawled_date=crawled_date)
    rss_vietnamplus_preprocessor(save_file=True, crawled_date=crawled_date)
    rss_tuoitre_preprocessor(save_file=True, crawled_date=crawled_date)
    


if __name__ == "__main__":
    run_preprocessors()
