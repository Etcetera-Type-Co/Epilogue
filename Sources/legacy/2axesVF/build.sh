#!/bin/sh
set -e

echo "Converting .glyphs to .ufo"
fontmake -g Sources/epilogue.glyphs -o ufo

echo "Generating Static fonts"
mkdir -p ./fonts ./fonts/static/ttf ./fonts/static/otf ./fonts/variable
fontmake --overlaps-backend pathops -m ./master_ufo/epilogue.designspace -i -o ttf --output-dir ./fonts/static/ttf/
fontmake --overlaps-backend pathops -m ./master_ufo/epilogue.designspace -i -o otf --output-dir ./fonts/static/otf/




echo "Generating Variable Font"
mkdir -p ./fonts/variable
fontmake -m ./master_ufo/epilogue.designspace -o variable --output-path ./fonts/variable/Epilogue[slnt,wght].ttf
statmake --stylespace Sources/stat.stylespace --designspace ./master_ufo/epilogue.designspace ./fonts/variable/Epilogue\[slnt\,wght\].ttf

rm -rf master_ufo/ instance_ufo/


echo "Post processing TTFs"
ttfs=$(ls ./fonts/static/ttf/*.ttf)
for ttf in $ttfs
do
	gftools fix-dsig -f $ttf;
	ttfautohint $ttf $ttf.fix
	[ -f $ttf.fix ] && mv $ttf.fix $ttf
	gftools fix-hinting $ttf
	[ -f $ttf.fix ] && mv $ttf.fix $ttf
done

echo "Post processing OTFs"
otfs=$(ls ./fonts/static/otf/*.otf)
for otf in $otfs
do
	gftools fix-dsig -f $otf
done



echo "Building webfonts"
rm -rf ./fonts/web/woff2
ttfs=$(ls ./fonts/static/ttf/*.ttf)
for ttf in $ttfs; do
    woff2_compress $ttf
done
mkdir -p ./fonts/web/woff2
woff2s=$(ls ./fonts/static/*/*.woff2)
for woff2 in $woff2s; do
    mv $woff2 ./fonts/web/woff2/$(basename $woff2)
done
#########
rm -rf ./fonts/web/woff
ttfs=$(ls ./fonts/static/ttf/*.ttf)
for ttf in $ttfs; do
    sfnt2woff-zopfli $ttf
done

mkdir -p ./fonts/web/woff
woffs=$(ls ./fonts/static/*/*.woff)
for woff in $woffs; do
    mv $woff ./fonts/web/woff/$(basename $woff)
done





echo "Post processing VFs"
vf=$(ls ./fonts/variable/Epilogue[slnt,wght].ttf)
gftools fix-nonhinting $vf $vf.fix
mv $vf.fix $vf
gftools fix-dsig --autofix $vf;
gftools fix-unwanted-tables --tables MVAR $vf

rm ./fonts/variable/*gasp*

woff2_compress ./fonts/variable/Epilogue[slnt,wght].ttf



echo "Complete!"
