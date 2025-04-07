#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 26 10:59:36 2018

@author: Fraser M Callaghan

Classes for building standardised imaging projects. 
Adapted for general use. 


"""


import os
import shutil
import datetime
## 
from hurahura import mi_subject, miresearch_main
from hurahura.mi_config import MIResearch_config
import spydcmtk
from ngawari import fIO

# ====================================================================================================
#       HELPERS
# ====================================================================================================
nameUnknown = 'NAME-Unknown'


# ====================================================================================================
#       ABSTRACT SUBJECT CLASS
# ====================================================================================================
class ZfMRFSubject(mi_subject.AbstractSubject):
    """
    An abstract subject controlling most basic structure
    """
    def __init__(self, subjectNumber, 
                        dataRoot=MIResearch_config.data_root_dir,
                        subjectPrefix=MIResearch_config.subject_prefix,
                        suffix="") -> None:
        mi_subject.AbstractSubject.__init__(self, subjectNumber=subjectNumber,
                                            dataRoot=dataRoot,
                                            subjectPrefix=subjectPrefix, 
                                            suffix=suffix)

        self.physiology_data_dir = MIResearch_config.params['parameters'].get("physiology_data_dir", None)
        self.sage_data_dir = MIResearch_config.params['parameters'].get("sage_data_dir", None)

    ### ----------------------------------------------------------------------------------------------------------------
    ### Overriding methods
    ### ----------------------------------------------------------------------------------------------------------------
    
    ### ----------------------------------------------------------------------------------------------------------------
    ### Methods
    ### ----------------------------------------------------------------------------------------------------------------
    def moveToNewRoot(self, destinationRootDir):
        self.archiveSubject(destinationRootDir)


    def getName_Date_str(self, INCLUDE_EXAMID=True):
        name = self.getName()
        name = name.replace(" ","_")
        name = name.replace("^","_")
        while "__" in name:
            name = name.replace("__","_")
        try:
            dbDate = self.getStudyDate()
            ss = f"{dbDate[2:4]}_{dbDate[4:6]}_{dbDate[6:8]}_{name}"
        except ValueError: # Likely from anonymised study
            ss = f"Scan_{name}" # Append 'Scan' incase name is empty
        if INCLUDE_EXAMID:
            dbExamID = self.getTagValue('StudyID')
            ss = f"{ss}_{str(dbExamID)}"
        return ss



    ### ----------------------------------------------------------------------------------------------------------------
    ### GATING
    ### ----------------------------------------------------------------------------------------------------------------
    def copyGatingToStudy(self):
        if self.physiology_data_dir is None:
            self.logger.error("physiology_data_dir is not set - set in config file")
            return
        stationName = self.getTagValue("StationName")
        if "3" in self.getTagValue("MagneticFieldStrength"):
            gatingDir = os.path.join(self.physiology_data_dir, stationName, 'gating')
        else:
            gatingDir = os.path.join(self.physiology_data_dir, stationName, 'gating')
        if not os.path.isdir(gatingDir):
            self.logger.error("Gating backup directory not accessible")
            return
        tStart, tEnd = self.getStartTime_EndTimeOfExam()
        tStart, tEnd = str(tStart), str(tEnd)
        doScan = self.getMetaDict()['StudyDate']
        t1 = datetime.datetime.strptime(str(doScan+tStart), '%Y%m%d%H%M%S')
        t2 = datetime.datetime.strptime(str(doScan+tEnd), '%Y%m%d%H%M%S')
        gatingFiles = os.listdir(gatingDir)
        c0 = 0
        for iFile in gatingFiles:
            parts = iFile.split('_')
            fileDate = datetime.datetime.strptime(parts[-4]+parts[-3]+parts[-2], '%m%d%Y%H%M%S')
            if (fileDate < t2) and (fileDate > t1):
                shutil.copy2(os.path.join(gatingDir, iFile), self.getMetaDir())
                c0 += 1
        self.logger.info(f"Copied {c0} gating files to Meta directory")
    

    ### ----------------------------------------------------------------------------------------------------------------
    ### SPECTRA
    ### ----------------------------------------------------------------------------------------------------------------
    def getSpectraDir(self):
        return self._getDir(['RAW', 'SPECTRA'], BUILD_IF_NEED=True)


    def hasSpectra(self):
        return len(os.listdir(self.getSpectraDir())) > 0


    def _findSpectraInSAGE(self):
        if self.sage_data_dir is None:
            self.logger.error("SPECTRA: sage_data_dir is not set - set in config file")
        # First we check based upon the KISPI sage directory structure (this is fast)
        patID = self.getTagValue("PatientID")
        studyID = self.getStudyID()
        if str(studyID) == "0":
            studyID = self.getTagValue("ScannerStudyID")
        self.logger.info(f"SPECTRA: searching for: patID {patID}, studyID: {studyID}") 
        if (patID is not None) and (studyID is not None):
            for iDir in os.listdir(self.sage_data_dir):
                if patID in iDir:
                    sageStudyDir = os.path.join(self.sage_data_dir, iDir, studyID)
                    if os.path.isdir(sageStudyDir):
                        self.logger.info(f"SPECTRA: found sage study directory: {sageStudyDir}") 
                        return sageStudyDir
                    else:
                        self.logger.warning(f"SPECTRA: Expect {sageStudyDir} but not found")    
        else:
            self.logger.warning(f"SPECTRA: Could not find sage dir because patID={patID}, studyID={studyID}")
        self.logger.info(f"SPECTRA: Could not find sage dir by patID....")
        ## 
        ## If we did not find a matching sage directory, then we check based upon StudyInstanceUID by 
        ## checking all the dicoms in the Sage archive (this is slow but should be more robust)
        studyInstanceUID = self.getTagValue("StudyInstanceUID")
        self.logger.info(f"SPECTRA: Searching using spydcmtk: studyInstanceUID={studyInstanceUID}") 
        listOfSage = spydcmtk.dcmTK.ListOfDicomStudies.setFromDirectory(self.sage_data_dir, HIDE_PROGRESSBAR=True, extn_filter=".dcm")
        matchingSageStudy = listOfSage.getStudyByTag("StudyInstanceUID", studyInstanceUID)
        if matchingSageStudy is not None:
            # Found a matching sage study - so return the directory
            sageStudyDir = matchingSageStudy.getTopDir()
            if os.path.isdir(sageStudyDir):
                self.logger.info(f"SPECTRA: found sage study directory: {sageStudyDir}") 
                return sageStudyDir
            else:
                # this should never be returned - possible if network issue
                self.logger.warning(f"SPECTRA: found sage study directory BUT is not a directory: {sageStudyDir}") 
        self.logger.warning(f"SPECTRA: Could not find sage study directory for: {self}") 
        return None # We failed to find any sage directory matching this study. 


    def copySpectraToStudy(self, FORCE=False):
        if (not FORCE) and self.hasSpectra():
            return 0
        if self.sage_data_dir is None:
            self.logger.error("SPECTRA: sage_data_dir is not set - set in config file")
        sageDir = self._findSpectraInSAGE()
        if sageDir is not None:
            shutil.copytree(sageDir, self.getSpectraDir(), dirs_exist_ok=True)
            self.logger.info('SPECTRA: Copy spectra to study: (%s, %s)'%(sageDir, self.getSpectraDir()))
            return 0
        return 1
    

    def getSpectraPDF_dict(self):
        specPDF_dict = {}
        for iDir in os.listdir(self.getSpectraDir()):
            try:
                int(iDir)
                thisSpectraDir = os.path.join(self.getSpectraDir(), iDir)
                specPDF_dict[iDir] = ''
                for iSub in os.listdir(thisSpectraDir):
                    if (iSub.startswith('P') and iSub.endswith('.7.PDF')):
                        specPDF_dict[iDir] = os.path.join(thisSpectraDir, iSub)
            except NameError:
                continue
        return specPDF_dict
    

    def isSpectraComplete(self):
        if not self.hasSpectra():
            return False
        spectraDict = self.getSpectraPDF_dict()
        pdfFiles_tf = [os.path.isfile(i) for i in spectraDict.values()]
        return all(pdfFiles_tf)


    ### ----------------------------------------------------------------------------------------------------------------
    ### DTI / T1 - these are just examples for some basic functionality
    ### ----------------------------------------------------------------------------------------------------------------
    def hasDTI(self):
        descList = self.getDicomFoldersListStr(FULL=False)
        tf = ['dti' in i.lower() for i in descList]
        return any(tf)


    def hasT1(self):
        descList = self.getDicomFoldersListStr(FULL=False)
        tf = ['t1' in i.lower() for i in descList]
        return any(tf)
    

    ### ----------------------------------------------------------------------------------------------------------------
    ### PROJECT
    ### ----------------------------------------------------------------------------------------------------------------
    def getProjectDir(self, projName, BUILD_IF_NEED=False):
        return self._getDir(["PROJECTS", projName], BUILD_IF_NEED=BUILD_IF_NEED)


    def getProjectMetaFile(self, projName, suffix="META", BUILD_IF_NEED=False):
        return os.path.join(self.getProjectDir(projName, BUILD_IF_NEED=BUILD_IF_NEED), f"{projName}_{suffix}.json")


    def getProjMetaDict(self, projName):
        jsonFile = self.getProjectMetaFile(projName=projName)
        if os.path.isfile(jsonFile):
            return mi_subject.spydcm.dcmTools.parseJsonToDictionary(jsonFile)
        return {}


    def updateProjMetaDict(self, projName, metaDict):
        jsonFile = self.getProjectMetaFile(projName, BUILD_IF_NEED=True)
        dd = self.getProjMetaDict(projName)
        dd.update(metaDict)
        fIO.writeDictionaryToJSON(jsonFile, dd)
        self.logger.info(f'Updated {projName} meta file')

# ====================================================================================================
# ====================================================================================================


### ====================================================================================================================
#      THIS IS ZFMRF SPECIFIC COMMAND LINE ACTIONS
### ====================================================================================================================
def zfmrf_specific_actions(args):
    if args.qName is not None: 
        for sn in args.subjNList:
            iSubj = args.MISubjClass(sn, args.dataRoot, args.subjPrefix, suffix=args.subjSuffix)
            if iSubj.exists():
                if args.qName.lower() in iSubj.getName().lower():
                    print(f"{args.qName} = {iSubj}")

    elif args.cpGating:
        for sn in args.subjNList:
            iSubj = args.MISubjClass(sn, args.dataRoot, args.subjPrefix, suffix=args.subjSuffix)
            if iSubj.exists():
                if args.DEBUG:
                    print(f"Copy gating: {iSubj.subjID}...")
                iSubj.copyGatingToStudy()

    elif args.cpSpectra:
        for sn in args.subjNList:
            iSubj = args.MISubjClass(sn, args.dataRoot, args.subjPrefix, suffix=args.subjSuffix)
            if iSubj.exists():
                if args.DEBUG:
                    print(f"Copy spectra: {iSubj.subjID}...")
                iSubj.copySpectraToStudy()

    elif args.pTags:
        for sn in args.subjNList:
            iSubj = args.MISubjClass(sn, args.dataRoot, args.subjPrefix, suffix=args.subjSuffix)
            if iSubj.exists():
                tags = iSubj.getMetaDict()
                tags.pop("Series")
                for ikey in sorted(tags.keys()):
                    print(f"{ikey} = {tags[ikey]}")

### ====================================================================================================================
### ====================================================================================================================


### ====================================================================================================================
#       ARGS SETUP
### ====================================================================================================================
def getArgGroup():
    groupZfmrf = miresearch_main.ParentAP.add_argument_group('ZFMRF Actions')
    groupZfmrf.add_argument('-qName', dest='qName', help='Query data by name', type=str, default=None)
    groupZfmrf.add_argument('-pTags', dest='pTags', help='Print Tags (except series)', action='store_true')
    groupZfmrf.add_argument('-cpGating', dest='cpGating', help='Copy gating data to study', action='store_true')
    groupZfmrf.add_argument('-cpSpectra', dest='cpSpectra', help='Copy spectra data to study', action='store_true')
    return groupZfmrf
    ##

def main():
    getArgGroup()
    ##
    miresearch_main.main(extra_runActions=[zfmrf_specific_actions], class_obj=ZfMRFSubject)


# S T A R T
if __name__ == '__main__':
    main()
