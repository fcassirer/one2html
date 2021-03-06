##One2HTM Copyright 2011 Eirinn Mackay
##        Updated June 2013 Fred Cassirer to support sectionGroups and attachments, lose the GUI

##This program is free software: you can redistribute it and/or modify
##it under the terms of the GNU General Public License as published by
##the Free Software Foundation, either version 3 of the License, or
##(at your option) any later version.
##
##This program is distributed in the hope that it will be useful,
##but WITHOUT ANY WARRANTY; without even the implied warranty of
##MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##GNU General Public License for more details.
##
##You should have received a copy of the GNU General Public License
##along with this program.  If not, see <http://www.gnu.org/licenses/>.

import email.parser
import win32com.client
import xml.etree.ElementTree as ET
import os
import pickle
import tempfile
import re
import ConfigParser
import shutil
from time import sleep
from operator import itemgetter

ignored_headings = ['OneNote_RecycleBin','New Section','Deleted Pages']

onapp = win32com.client.Dispatch( 'OneNote.Application')

### HTML generation routines (most of them) ###

#CSS style for index pages
commonheader="""<html><head><meta name="viewport" content="width = device-width"><style>
body { font-family:Calibri; margin:0px; padding:8px;}
div {padding: 4px; line-height: 24pt; max-width: 900px; border-top: solid grey thin; font-size: large;}
div.subpage { margin-left: 30px; max-width: 870px; font-size:medium;}
a { text-decoration: none; color: black;}
a:hover{ text-decoration: underline overline;}
a.divlink {display:block;}
h1 {font-size: 24pt; font-weight: normal; margin: 1px;}
breadcrumb {display: block; margin-bottom: 1em; font-style: italic; font-size: small}
</style>\n"""

#CSS style for exported onenote pages
customcss="<style>ul, ol {padding-left:0px;margin-left:0px;list-style-position:inside;}</style>"

#classes for the index pages
class IndexMaker: #root class, never instantiated
    def start(self):
        self.html=commonheader+self.firstline
        self.completed=False
    def add(self, attribDict):
        self.html=self.html+self.linetemplate.format(**attribDict)
    def insertText(self, text):
        self.html=self.html+text
    def getHTML(self):
        if not self.completed:
            self.html=self.html+'</body></html>'
            self.completed=True
        return self.html
    def writeFile(self, fullpath):
        folder=os.path.dirname(fullpath)
        if not os.path.isdir(folder): os.makedirs(folder)
        fs=open(fullpath, 'w')
        fs.write(self.getHTML().encode('utf-8'))
        fs.close()
        
class RootIndex(IndexMaker):
    def __init__(self):
        self.firstline=u'<title>Notebooks</title></head><body><h1>Notebooks</h1>\n'
        self.linetemplate=u'<div><a class="divlink" href="{name}/index.htm">{name}</a></div>\n'
        self.start()
class NotebookIndex(IndexMaker):
    def __init__(self, attribDict):
        self.firstline=u'<title>{name}</title></head><body><h1>{name}</h1>'.format(**attribDict)
        self.firstline+self.firstline+u'<breadcrumb><a href="../index.htm">&lArr; back to notebook list</a></breadcrumb>'
        self.linetemplate=u'<div style="background: {color}"><a class="divlink" href="{name}.htm">{group}{name}</a></div>\n'
        self.start()
class SectionIndex(IndexMaker):
    def __init__(self, attribDict):
        self.firstline=u'<title>{name}</title></head><body style="border-left: solid {color} 10px;"><h1>{group}{name}</h1>'.format(**attribDict)
        self.firstline+self.firstline+u'<breadcrumb><a href="index.htm">&lArr; back to section list</a></breadcrumb>'
        self.linetemplate=u'<div {subpageString}><a class="divlink" href={permanentID}/index.htm>{name}</a></div>'
        self.start()

### end of HTML routines ###

   
class One2HTM:
    def __init__(self, master):
        self.master=master #master refers to the main window
        #process configuration file. If this returns true then we can continue.
        if self.DoConfig():
            self.outputText('Destination folder is %s' % self.rootFolder)
            #initialise variables
            self.timestamps={}
            self.recentpages={}
            self.counter=0
            if self.loadTimestamps():
                self.outputText("Sync list found at destination.")
            else:
                self.outputText("No sync list found; entire tree will be built.")
            allnotebooks = self.getNotebooks()
            if not self.noteBooks:
                self.noteBooks = allnotebooks
            self.counter=self.refreshRate #doing this ensure a scan when the timer first fires
            self.firstscan=True
            self.scan()
#            master.Bind(wx.EVT_TIMER, self.onTimer, master.timer)
#            master.timer.Start(1000, oneShot=True) #a one-shot timer is safer in case of exceptions
        else:
            master.Close(True)

    def onTimer(self, event): #this event fires every second
        self.counter=self.counter+1
        if self.counter>self.refreshRate:
            self.counter=0
            self.scan()
        self.master.timer.Start(1000, oneShot=True)

    def DoConfig(self):
        config=ConfigParser.ConfigParser()
        config.read('One2HTM.ini')
        if config.has_section('Main'):
            self.rootFolder=config.get('Main','Destination')
            self.refreshRate=config.getint('Main','RefreshRateInSeconds')
            self.maxRecentItems=config.getint('Main','MaxRecentItems')
            # Support a list of notebooks in the .ini file, syntax:
            # notebooks =
            #  one
            #  two
            #  three
            #
            # Must be a leading space, one notebook per line
            try:
                self.noteBooks=re.sub(r'^\n',r'',config.get('Main','NoteBooks')).split('\n')
            except:
                self.noteBooks=''
            return True
        else:
            #            dirdialog=wx.DirDialog(self.master, 'Select destination folder for HTML files')
            #            dirdialog.ShowModal()
            self.rootFolder=dirdialog.GetPath()
            if self.rootFolder:
                self.refreshRate=60
                self.maxRecentItems=5
                config.add_section('Main')
                config.set('Main','Destination',self.rootFolder)
                config.set('Main','RefreshRateInSeconds',self.refreshRate)
                config.set('Main','MaxRecentItems',self.maxRecentItems)
                config.write(open('One2HTM.ini','w'))
                return True
            else: return False
            
    def outputText(self, text):
        #convenience function for putting text in the memobox
#        self.master.memo.AppendText(text+'\n')
        try:
            print text.encode('utf-8')+'\n'
        except UnicodeEncodeError:
            print "Couldn't print out text string because of unicode error\n"
            
    def loadTimestamps(self):
        ##reads the last-modified timestamp for each file
        ##this is crucial for syncing just the updated pages
        timestampsfilename=os.path.join(self.rootFolder, "timestamps.txt")
        if os.path.isfile(timestampsfilename):
            tsf=open(timestampsfilename, 'rb')
            self.timestamps=pickle.load(tsf)
            tsf.close()
            return True
        else: return False
    def saveTimestamps(self):
        ##saves the last-modified timestamp for each file
        ##this is crucial for syncing just the updated pages
        timestampsfilename=os.path.join(self.rootFolder, "timestamps.txt")
        tsf=open(timestampsfilename, 'wb')
        pickle.dump(self.timestamps, tsf)
        tsf.close()
    def getNotebooks(self):
        ##just a little function to get the list of notebooks,
        ##to prove that the system is working
        ##First, get the OneNote XML data
        basexmlstring=onapp.GetHierarchy("",4) #4 is the scope level for pages
        root=ET.fromstring(basexmlstring.encode('utf-8'))
        notebooklist=[child for child in root if child.tag.endswith('Notebook')]
        self.outputText('Notebooks found: %s' % len(notebooklist))
        nlist=[]
        for notebook in [child for child in root if child.tag.endswith('Notebook')]:
            self.outputText('--'+notebook.get('name'))
            nlist.append(notebook.get('name'))
        return nlist
    def setChangedFlag(self, node):
        ##check if the page has changed since we last synced
        nodeID=node.get('permanentID', default=node.get('ID')) #get the permanentID if it has one 
        nodeTime=node.get('lastModifiedTime')
        node.set('hasChanged',self.timestamps.get(nodeID)<>nodeTime)
        self.timestamps[nodeID]=nodeTime
    def getPermanentPageID(self, pageID):
        ##converts a pageID (which can change under various circumstances) to a hyperlink ID (which doesn't change)
        hyperlink=onapp.GetHyperlinkToObject(pageID,'')
        regex=re.compile(r'section-id=([\w\{\}-]*)&page-id=([\w\{\}-]*)')
        ids=re.findall(regex, hyperlink) #id[0]=sectionid, id[1]=pageid
        if ids: return ids[0][1]
        
    def getNewPages(self, notebook):
        ##generates the recently-changed-page list
        newpagelist='<br><h1>Recent pages</h1>\n'
        for page in self.recentpages.get(notebook.get('name'),[]):
            newpagelist=newpagelist+'<div style="background: %(color)s" ><a class="divlink" href=%(permanentID)s/index.htm>%(sectionname)s &raquo;<br> %(name)s</a></div>\n' % page
        return newpagelist 

    def addPageDate(self, page, notebook):
        ##records the most recently changed pages
        plist=self.recentpages.get(notebook.get('name'),[])
        #plist is a list of dictionaries containing attributes about each page
        #first, check to see if the current page is on this list
        idlist=[p['permanentID'] for p in plist]
        if page.get('permanentID') in idlist:
            plist[idlist.index(page.get('permanentID'))]=page.attrib
        else:
            #check if the page is newer than the last item on this list (if there is one)
            if not plist or page.get('lastModifiedTime')>=plist[-1]['lastModifiedTime']:
                plist.append(page.attrib)
        plist.sort(key=itemgetter('lastModifiedTime'),reverse=True) #now sort the list (again)
        del plist[self.maxRecentItems:] #remove any items beyond the 5th
        self.recentpages[notebook.get('name')]=plist

    ## Major functions here ##
    def scan(self):
        ## Iterate through the notebooks and identify changed pages to be exported ##
        #        self.master.SetStatusText('Scanning...')     
        basexmlstring=onapp.GetHierarchy("",4) #4 is the scope level for pages
        root=ET.fromstring(basexmlstring.encode('utf-8'))
        rootChanged=False #this has to be done manually because the root doesn't have a Last Modified. This variable is changed at the end of the loop.
        rootindex=RootIndex()
        for notebook in [child for child in root if child.tag.endswith('Notebook')]:
            if (notebook.get('name') in self.noteBooks):
                rootindex.add(notebook.attrib)
                self.setChangedFlag(notebook)
                if notebook.get('hasChanged') or self.firstscan: #let's look at the sections in this notebook
#                   self.master.SetStatusText('Updating...')
                    notebookindex=NotebookIndex(notebook.attrib)

                    for child in notebook:
                        self.scanObject('',child, notebook, notebookindex)

                    #find the most recently-updated pages
                    notebookindex.insertText(self.getNewPages(notebook))
                    notebookindex.writeFile(os.path.join(self.rootFolder, notebook.get('name'), 'index.htm'))
                    rootChanged=True
            if rootChanged: #this means something, somewhere has changed. Update the root index and the timestamp list
                rootindex.writeFile(os.path.join(self.rootFolder, 'index.htm')) #updating this index not really necessary but it doesn't hurt
                self.saveTimestamps()
            self.firstscan=False
            #        self.master.SetStatusText("Scanning for changes every %s seconds" % self.refreshRate)
        return rootChanged

    def scanObject(self, prefix, sectionobject, notebook, notebookindex):
        if (sectionobject.get('name') not in ignored_headings):   # Skip these sections
            print sectionobject.tag + " >" + sectionobject.get('name') + "<"
            if prefix: prefix + '=> '
            sectionobject.set('group',prefix)
            if sectionobject.tag.endswith('Section'):
                    notebookindex.add(sectionobject.attrib)
                    print "attrib:",sectionobject.attrib
                    self.scanSection(prefix, sectionobject, notebook)
            if sectionobject.tag.endswith('SectionGroup'):
                for section in sectionobject:
                    section.set('group',prefix + sectionobject.get('name') +'=> &raquo; ')
                    self.scanObject(prefix + sectionobject.get('name') + '=> ', section, notebook, notebookindex)

    def scanSection(self, prefix, section, notebook): #run through all the pages in this section
        self.setChangedFlag(section) 
        if section.get('hasChanged') or self.firstscan:
            sectionindex=SectionIndex(section.attrib)
            for page in [child for child in section if child.tag.endswith('Page')]:
                if (page.get('name') not in ignored_headings):   # Skip these sections
                    page.set('permanentID',self.getPermanentPageID(page.get('ID')))
                    page.set('color',section.get('color'))
                    page.set('sectionname',prefix + '=>' + section.get('name'))
                    page.set('group',prefix)
                    if page.get('isSubPage') or page.get('pageLevel')=='2':
                        page.set('subpageString','class="subpage"')
                    else:
                        page.set('subpageString','')
                    sectionindex.add(page.attrib)
                    self.setChangedFlag(page)
                    self.addPageDate(page, notebook)
                    if page.get('hasChanged'):
                        self.outputText(notebook.get('name')+'\\'+section.get('name')+'\\'+page.get('name'))
                        #                    wx.Yield() #refresh the gui
                        self.exportPage(notebook.get('name'), page)
            sectionindex.writeFile(os.path.join(self.rootFolder, notebook.get('name'), section.get('name')+'.htm'))

    def exportPage(self, notebookname, page):
        ## converts a onenote page into a set of HTML pages ##
        #first, some sub-functions
        def writeHTML(text):
            ##this function saves the HTML file
            #insert custom CSS
            text=text.replace('<head>','<head><title>'+page.get('name').encode('utf-8')+'</title>'+customcss)
            #remove unnecessary left margins
            text=re.sub(r'margin-left:[-.\d]*in;','',text)
            #replaces onenote hyperlinks with ones to the correct web page
            text=re.sub(r'href=.*section-id=([\w\{\}-]*)&amp;page-id=([\w\{\}-]*).*">',r'href="../\2/index.htm">',text)
            #replaces onenote inserted files with local links to the copied files
            rex=re.compile('&lt;&lt;(?P<file>[^;]*)&gt;&gt;')
            files=re.finditer(rex,text)
            for match in files:
                # Handle annoying extra spaces \n's in filenames left by onapp.Publish()
                #  Note that this will not produce correct links if a file has multiple spaces in the name ...
                nonl=re.sub(r'[\n ]+',r' ',match.group('file'))  
                text=re.sub(r'&lt;&lt;([^;]*)&gt;&gt;',r'<a class="divlink" href="'+nonl+'">'+nonl+';</div>',text,1)  # Fixup each attachment
            if not os.path.isdir(destinationfolder):
                os.makedirs(destinationfolder)
            outfilename=os.path.join(destinationfolder,'index.htm')
            outfile=open(outfilename,'w')
            outfile.write(text)
            outfile.close()
        def writeFile(filename, content):
            ##this function saves non-HTML files like images
            fulldir=os.path.join(destinationfolder,'index_files')
            if not os.path.isdir(fulldir):
                os.makedirs(fulldir)
            outfile=open(os.path.join(fulldir, filename),'wb')
            outfile.write(content)
            outfile.close()
        def copyInsertedFiles(page,destinationfolder):
            # Pull out all of the attachments and copy them locally
            xml = ET.fromstring(onapp.GetPageContent(page.get('ID'),'').encode('utf-8'))
            for e in xml.iter():
                if (e.tag.endswith('InsertedFile')):
                    print 'Inserted File:', e.get('preferredName')," ",e.get('pathSource')
                    try:
                        targetfile=os.path.join(destinationfolder,e.get('preferredName'))
                        if os.path.isfile(targetfile): # any existing file must be removed, otherwise an exception occurs
                            os.remove(targetfile)
                        shutil.copyfile(e.get('pathCache'),targetfile)
                    except:
                        path=e.get('pathCache')
                        print "Couldn't copy file ",path.encode('utf-8')
                        raise

        ##export the onenote page into a temporary MHT file
        mhtfilename=os.path.join(tempfile.gettempdir(), 'index.mht')
        if os.path.isfile(mhtfilename): # any existing file must be removed, otherwise an exception occurs
            os.remove(mhtfilename)
        onapp.Publish(page.get('ID'),mhtfilename,2,'') #this makes the MHT file
        destinationfolder=os.path.join(self.rootFolder, notebookname, page.get('permanentID'))

        if not os.path.isdir(destinationfolder):
            os.makedirs(destinationfolder)
        
        # Grab any attachments now that the folder has been created
        copyInsertedFiles(page,destinationfolder)

        #now convert the MHT file into HTML and write to the destination:        
        fp=open(mhtfilename)
        try:
            mimeparser=email.parser.Parser()
            body=mimeparser.parse(fp)
            if not body.is_multipart():
                writeHTML(body.get_payload(decode=True))
            else:
                parts=body.get_payload()
                for part in parts:
                    if part.has_key('Content-Location'):
                        location=part['Content-Location']
                        if location.endswith('index.htm'):
                            writeHTML(part.get_payload(decode=True))
                        else:
                            if 'index_files' in location:
                                filename=location.partition('index_files/')[2]
                                writeFile(filename, part.get_payload(decode=True))
            return body
        finally:
            fp.close()
    ## End of the major functions ##

        
base=One2HTM("foo")

