#!/bin/sh
set -e

echo "Generating Fonts"
mkdir -p ./fonts/static/ttf
fontmake -g Sources/Epilogue.glyphs -i --family-name "Epilogue" -o ttf --output-dir ./fonts/static/ttf/

mkdir -p ./fonts/static/otf
fontmake -g Sources/Epilogue.glyphs -i --family-name "Epilogue" -o otf --output-dir ./fonts/static/otf/

mkdir -p ./fonts/variable
fontmake -g Sources/Epilogue.glyphs -o variable --output-path ./fonts/variable/Epilogue[slnt,wght].ttf

statmake --stylespace Sources/stat.stylespace --designspace ./master_ufo/Epilogue.designspace ./fonts/variable/Epilogue\[slnt\,wght\].ttf

rm -rf master_ufo/ instance_ufo/



# ============================================================================
# Autohinting ================================================================


echo "Post processing TTFs"
ttfs=$(ls ./fonts/static/ttf/*.ttf)
for ttf in $ttfs
do
	gftools fix-dsig -f $ttf;
	ttfautohint $ttf $ttf.fix
	mv "$ttf.fix" $ttf;
	gftools fix-hinting $ttf
	mv "$ttf.fix" $ttf;
done

echo "Post processing OTFs"
otfs=$(ls ./fonts/static/otf/*.otf)
for otf in $otfs
do
	gftools fix-dsig -f $otf
done



# ============================================================================
# Build woff2 fonts ==========================================================
# requires https://github.com/bramstein/homebrew-webfonttools

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
# ============================================================================
# Build woff fonts ==========================================================
# requires https://github.com/bramstein/homebrew-webfonttools

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

woff2_compress ./fonts/variable/Epilogue[slnt,wght].ttf





echo "Post processing VFs"

vfs=$(ls ./fonts/variable/*.ttf)
for vf in $vfs
do
	gftools fix-dsig -f $vf;
	gftools fix-nonhinting $vf "$vf.fix";
	mv "$vf.fix" $vf;
	ttx -f -x "MVAR" $vf; # Drop MVAR. Table has issue in DW
	rtrip=$(basename -s .ttf $vf)
	new_file=./fonts/variable/$rtrip.ttx;
	rm $vf;
	ttx $new_file
	rm ./fonts/variable/*.ttx
done

rm ./fonts/variable/*backup*.ttf

echo "Complete!"
