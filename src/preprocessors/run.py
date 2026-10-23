from .rss_vnexpress import rss_vnexpress_preprocessor
from .rss_vietnamplus import rss_vietnamplus_preprocessor
from .rss_tuoitre import rss_tuoitre_preprocessor


def run_preprocessors():
    rss_vnexpress_preprocessor(save_file=True)
    rss_vietnamplus_preprocessor(save_file=True)
    rss_tuoitre_preprocessor(save_file=True)
    


if __name__ == "__main__":
    run_preprocessors()
