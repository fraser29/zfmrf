#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 26 10:59:36 2018

@author: Fraser M Callaghan

Classes for building standardised imaging projects. 
Adapted for general use. 


"""


import os
import csv
import shutil
import datetime
import subprocess
## 
from hurahura import mi_subject, miresearch_main
from hurahura.mi_config import MIResearch_config
import spydcmtk
from ngawari import fIO

# ====================================================================================================
#       HELPERS
# ====================================================================================================
nameUnknown = 'NAME-Unknown'



def run_command(cmd):
    result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout

def parse_csv_from_output(output, start_header="SubjectID"):
    """Parses CSV part of output starting from a known header line"""
    lines = output.strip().splitlines()
    header_index = next(i for i, line in enumerate(lines) if start_header in line)
    csv_lines = lines[header_index:]
    reader = csv.DictReader(csv_lines)
    return list(reader)

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
        self.dicom_server_ip = MIResearch_config.params['parameters'].get("dicom_server_ip", None)

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
    def getNumberOfDICOMS_Autorthanc(self):
        """Get the number of DICOMS in the Autorthanc server.
        """
        if self.dicom_server_ip is None:
            raise ValueError("DICOM server IP is not set - set in config file")
        thisStudyInstanceUID = self.getTagValue('StudyInstanceUID')
        cmd = f"pourewa -u {self.dicom_server_ip} -tag StudyInstanceUID {thisStudyInstanceUID}"
        output = run_command(cmd)
        data = parse_csv_from_output(output, start_header="SubjectID")
        result_dict = {row['StudyInstanceUID']: row for row in data}
        if thisStudyInstanceUID in result_dict:
            return result_dict[thisStudyInstanceUID]['NumberOfDICOMS']
        else:
            return 0

    @mi_subject.ui_method(description="Check if the number of DICOMS in the subject directory and the number of DICOMS in the Autorthanc server are equal", category="ZFMRF", order=1)
    def isNumberOfDICOMS_vs_Autorthanc_equal(self):
        """Check the number of DICOMS in the subject directory and the number of DICOMS in the Autorthanc server.
        """
        numDICOMS_autorthanc = self.getNumberOfDICOMS_Autorthanc()
        numDICOMS_local = self.countNumberOfDicoms()
        return numDICOMS_local == numDICOMS_autorthanc


    ### ----------------------------------------------------------------------------------------------------------------
    ### SEND TO DICOM SERVER
    ### ----------------------------------------------------------------------------------------------------------------
    def _sendDirectoryToAutorthanc(self, directoryToSend):    
        print(f"WARNING: _sendDirectoryToAutorthanc is deprecated - use sendDirectoryToAutorthanc instead")
        return self.sendDirectoryToAutorthanc(directoryToSend)
        
    def sendDirectoryToAutorthanc(self, directoryToSend):
        """Send a directory of DICOMS to ZfMRF instance of AUTORTHANC. 
        Uses opensource package pourewa to connect and upload images to AUTORTHANC


        Args:
            directoryToSend (str): directory of DICOMS to send (e.g. your post-processed images)

        Raises:
            RuntimeError: If failure for the call to pourewa

        Requires: 
            self.dicom_server_ip: Should be set in conf file and read

        Returns:
            int: 0 for success, otherwise 1
        """
        if self.dicom_server_ip is not None:
            if len(os.listdir(directoryToSend)) > 0:
                cmd = f"pourewa -u {self.dicom_server_ip} -l {directoryToSend}"

                self.logger.info(f"Uploading {self.subjID} to autorthanc")
                try:
                    self.logger.debug(f"Upload command: {cmd}")
                    result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
                    self.logger.debug(f"Upload command output: {result.stdout}")
                    return 0
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"Failed to upload to autorthanc: {e}")
                    self.logger.error(f"Command output: {e.stderr}")
                    raise RuntimeError("Failed to upload DICOMs to autorthanc server") from e
        else:
            self.logger.error(f"DICOM server IP is {self.dicom_server_ip}")
        return 1



    ### ----------------------------------------------------------------------------------------------------------------
    ### GATING
    ### ----------------------------------------------------------------------------------------------------------------
    def getPhysiologicalDataDir(self):
        return self._getDir(["RAW", "PHYSIOLOGICAL_DATA"])


    @mi_subject.ui_method(description="Copy gating data to study", category="ZFMRF", order=10)
    def copyGatingToStudy(self):
        """Will find the Physiology data appropriate for your study and copy to directory:
        self.getPhysiologicalDataDir() ==> SUBJID/RAW/PHYSIOLOGICAL_DATA
        """
        if self.physiology_data_dir is None:
            self.logger.error("physiology_data_dir is not set - set in config file")
            return
        if not os.path.isdir(self.physiology_data_dir):
            self.logger.error(f"physiology_data_dir is not a directory: {self.physiology_data_dir}")
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
            if iFile.startswith('SPU'):
                dos = parts[1][:8]
                HH = parts[1][-2:]
            else:
                dos = parts[-4][:8]
                HH = parts[-4][-2:]
            try:
                fileDate = datetime.datetime.strptime(dos+HH+parts[-3]+parts[-2], '%m%d%Y%H%M%S')
            except ValueError:
                self.logger.warning(f"Could not parse date from {iFile}")
                continue
            if (fileDate < t2) and (fileDate > t1):
                shutil.copy2(os.path.join(gatingDir, iFile), self.getPhysiologicalDataDir())
                c0 += 1
        self.logger.info(f"Copied {c0} gating files to Meta directory")
        return 0
    

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


    @mi_subject.ui_method(description="Copy spectra data to study", category="ZFMRF", order=10)
    def copySpectraToStudy(self, FORCE=False):
        """Find spectra data matching this study and copy to:
        self.getSpectraDir() ==> SUBJID/RAW/SPECTRA

        Args:
            FORCE (bool, optional): Should copy if already present. Defaults to False.

        Returns:
            int: 0 for success else 1
        """
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
    ### ARCHIVED DATA
    ### ----------------------------------------------------------------------------------------------------------------
    def getMRIDataFromArchive(self, archiveDir):
        self.logger.debug(f"Getting MRI archive data for {self.subjID} from {archiveDir} ")
        patientID = self.getTagValue("PatientID", ifNotFound=None)
        if patientID is None:
            raise ValueError(f"Patient ID not found for {self.subjID}")
        
        dos = self.getTagValue("StudyDate", ifNotFound=None)
        examID = self.getTagValue("StudyID", ifNotFound=None)
        if dos is None:
            raise ValueError(f"StudyDate not found for {self.subjID}")
        if examID is None:
            raise ValueError(f"ExamID not found for {self.subjID}")
        
        remotePatientDir = None
        for iSubDir in os.listdir(archiveDir):
            if iSubDir.startswith(f"_{patientID}"):
                remotePatientDir = os.path.join(archiveDir, iSubDir)
        if remotePatientDir is None:
            raise ValueError(f"Can not find remotePatientDir for {self.subjID} w patID: {patientID}")
        possibleMatches = []
        for iDir in os.listdir(remotePatientDir):
            if (dos in iDir) and (examID in iDir):
                possibleMatches.append(os.path.join(remotePatientDir, iDir))
        self.logger.debug(f"Found {len(possibleMatches)} archive to load from")
        for iArchive in possibleMatches:
            self.logger.info(f"Loading DICOMS from {iArchive}")
            dcmStudies = spydcmtk.dcmTK.ListOfDicomStudies.setFromInput(iArchive)
            for iStudie in dcmStudies:
                self.loadSpydcmStudyToSubject(iStudie)
         
 
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
    subjList = mi_subject.SubjectList([MIResearch_config.class_obj(sn, MIResearch_config.data_root_dir, MIResearch_config.subject_prefix, suffix=args.subjSuffix) for sn in args.subjNList])
    if args.DEBUG: 
        for iSubj in subjList:
            iSubj.logger.setLevel("DEBUG")


    if args.qName is not None: 
        subjList.reduceToExist()
        for iSubj in subjList:
            if args.qName.lower() in iSubj.getName().lower():
                print(f"{args.qName} = {iSubj}")

    elif args.cpGating:
        subjList.reduceToExist()
        for iSubj in subjList:
            iSubj.copyGatingToStudy()

    elif args.cpSpectra:
        subjList.reduceToExist()
        for iSubj in subjList:
            iSubj.copySpectraToStudy()

    elif args.pTags:
        subjList.reduceToExist()
        for iSubj in subjList:
            tags = iSubj.getMetaDict()
            tags.pop("Series")
            for ikey in sorted(tags.keys()):
                print(f"{ikey} = {tags[ikey]}")

    elif args.pullDicomsFromRemote is not None:
        subjList.reduceToExist()
        for iSubj in subjList:
            iSubj.getMRIDataFromArchive(args.pullDicomsFromRemote)
        

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
    groupZfmrf.add_argument('-pullDICOMS', dest='pullDicomsFromRemote', 
                            help='Pull DICOMS from remote archive - give archive directory', type=str, default=None)
    return groupZfmrf
    ##

def main():
    getArgGroup()
    ##
    miresearch_main.main(extra_runActions=[zfmrf_specific_actions], class_obj=ZfMRFSubject)


# S T A R T
if __name__ == '__main__':
    main()
