# zfmrf

Zfmrf

This is a generic package for managing projects in the ZfMRF lab. 

## Installation

```bash
git clone https://github.com/fraser29/zfmrf.git
cd zfmrf
pip install -e .
```

## Usage

This package is designed to be used with the [hurahura](https://github.com/fraser29/hurahura) package.

ZfMRFSubject is a subclass of hurahura.mi_subject.AbstractSubject. One should subclass this class to create a new subject class to take advantage of the ZfMRF specific methods.


## Changelog

### 0.0.8
- Added support for SPU gating files

### 0.0.6 & 7
- Added felxibility around getting physiological gating files 
  
### 0.0.5
- Added UI decoration for checking DICOMS and getting physiological data.

### 0.0.4

- Added support for SPU gating files
- Error catching on gating file parsing