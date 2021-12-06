# prose

<p align="center">

  <img width="450" src="https://github.com/lgrcia/prose/blob/0.9.6/docs/source/prose_illustration.png">
  <br>  
  <br>
  A python framework to build FITS images pipelines.
  <br>
  <p align="center">
    <a href="https://github.com/lgrcia/prose">
      <img src="https://img.shields.io/badge/github-lgrcia/prose-blue.svg?style=flat" alt="github"/>
    </a>
    <a href="https://prose.readthedocs.io/en/latest/">
      <img src="https://img.shields.io/badge/read-thedoc-black.svg?style=flat" alt="read the doc"/>
    </a>
    <a href="">
      <img src="https://img.shields.io/badge/license-MIT-lightgray.svg?style=flat" alt="license"/>
    </a>
  </p>
</p>

 *prose* is a tool to build pipelines dedicated to astronomical images processing, *only based on pip installable dependencies* (e.g. no IRAF, Sextractor or Astrometry.net install needed 🎉). It features default pipelines to perform common tasks (such as automated calibration, reduction and photometry) and makes building custom ones easy.


```python

from prose.pipeline import Calibration, AperturePhotometry

destination = "reduced_folder"

reduction = Calibration(images=[...], flats=[...])
reduction.run(destination)

photometry = AperturePhotometry(destination)
photometry.run()

```

## Installation

prose runs more safely in its own [virtual environment](https://docs.python.org/3/tutorial/venv.html) and is tested on Python 3.6.

### example on OSX

create your [virtualenv](https://docs.python.org/3/tutorial/venv.html) and activate it

```shell
python3.6 -m venv prose_env
source prose_env/bin/activate.bin
```

Then to locally install prose

```shell
git clone https://github.com/lgrcia/prose.git
python3.6 -m pip install -e prose
```

Applicable to Linux-based and Windows OS