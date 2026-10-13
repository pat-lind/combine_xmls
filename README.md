LLM (GPT 5.6) generated script to assist with combining two separate folders each containing different types of XMLs formatted for neurolucida. 
One type of XML contains groups of points that define contours. The other type of XML contains points that define cell locations.

No extra libraries need to be installed.

### USAGE:

python combine_xmls.py "Path/To/Folder_With_cell_mappings" "Path/To/Folder_with_contours" "Path/To/Output_folder"

i.e. :
python combine_xmls.py "C:\Users\patri\OneDrive\Documents\marmlab\cell mappings" "C:\Users\patri\OneDrive\Documents\marmlab\Segmentations" "C:\Users\patri\OneDrive\Documents\marmlab\combined xml"


